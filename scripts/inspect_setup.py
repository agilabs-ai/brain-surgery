"""Read-only, bounded local inventory and transcript normalization.
No execution of skills; no uploads; no automatic calls to any model.
Only explicitly scoped projects/roots. Unknown log formats stay unknown.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from runtime_io import write_json, file_digest

SKIP_DIRS = {'.git','node_modules','.venv','venv','__pycache__','runs','reports'}
# The whole-file cap that used to skip any transcript larger than this. It made the
# scan silently drop 30 of 58 real logs. Transcripts are streamed line by line now;
# the constant is kept only so the regression test can say "bigger than the old cap".
LEGACY_PER_FILE_CAP = 3 * 1024 * 1024
# Every limit below is a runaway guard, never a sampling knob. A cap that binds on
# a normal machine ends up setting the headline instead of the setup doing it, which
# is the bug that made a 30 session cap report 179 dormant and a 400 session cap 167.
#
# Codex writes single rows up to 27MB, and the old 4MB row limit dropped them. The
# line is already in memory by the time this is checked (iterating a file yields the
# whole line), so the limit only avoids the parse, not the allocation.
MAX_LINE_BYTES = 64 * 1024 * 1024
MAX_LOG_ROWS = 400000                   # per transcript
# Measured on a heavily used machine: 9.3GB of transcripts, 302 sessions, 62s. The
# old 4GB budget cut that to 101 sessions and moved the headline from 81 to 87
# percent dormant while saving no time at all, because the wall clock is directory
# walking, not reading. This is now high enough that it does not bind in practice.
MAX_TOTAL_BYTES = 64 * 1024 * 1024 * 1024
MAX_SCAN_FILES = 20000
MAX_INVENTORY = 2000
#: How recently a skill must have been reached for a missing SKILL.md to be worth
#: reporting. Beyond this it is a skill the user removed, not a broken reference.
STALE_GAP_DAYS = 7

#: A Codex skill load: the agent reading `<...>/skills/<name>/SKILL.md` in a shell
#: command. Anchored on a `skills` path segment so an unrelated SKILL.md, or one
#: being edited rather than used, is not counted as usage.
CODEX_SKILL_READ = re.compile(r'skills/(?P<name>[A-Za-z0-9_.-]+)/SKILL\.md')


#: Paths the walk could not enter, collected so a scan can say its inventory is
#: incomplete rather than silently reporting a smaller machine than it found.
#: Module-level because `bounded_files` is a generator consumed in several places.
unreadable: list[str] = []


#: Row shapes only one host writes. Codex wraps everything in `payload`; Claude
#: puts the turn in `message`. Either alone is weak, so both are counted and the
#: larger pile wins.
CODEX_MARKERS = {'session_meta', 'response_item', 'event_msg', 'turn_context'}


def detect_host(rows: list[Any]) -> str:
    """Which agent wrote this transcript.

    The first version looked for a single `session_meta` row in the first 20 lines
    and assumed Claude otherwise. A Codex rollout without that marker near the top,
    a fragment or a resumed session, was then parsed with Claude rules, and every
    skill load in it was lost in silence. On a machine running both agents that
    quietly halves the evidence.

    Counting shapes instead of trusting one marker. A file that looks like neither
    is called Claude, because that host is the more common default and normalize()
    reports `invocation_coverage: unrecognized` for it either way, so the guess is
    visible in the output rather than buried.
    """
    codex = claude = 0
    for row in rows[:400]:
        if not isinstance(row, dict):
            continue
        if row.get('type') in CODEX_MARKERS or isinstance(row.get('payload'), dict):
            codex += 1
        elif isinstance(row.get('message'), dict):
            claude += 1
    return 'codex' if codex > claude else 'claude'


def bounded_files(root: Path, name: str, ceiling: int = MAX_SCAN_FILES):
    """Walk a root and yield matching files, following symlinks under guard.

    Skill roots are routinely assembled out of symlinks: one canonical copy of a
    skill, linked into every host directory that should see it. Refusing to follow
    them skipped 116 of the 197 entries in one real `~/.claude/skills`, and called
    skills dormant that the agent loads every day. That is not a conservative
    reading of a setup, it is the wrong one, and it lands on the headline number.

    Following links needs guards of its own. Each directory is resolved before it
    is entered and a directory already visited is not entered a second time, which
    ends a cycle and stops a link into a shared parent from being walked twice. The
    file ceiling still bounds the walk, so a link into a huge tree costs a capped
    number of stats rather than the session.
    """
    if not root.is_dir():
        return
    if not os.access(root, os.R_OK | os.X_OK):
        unreadable.append(str(root))
        return
    walked=0
    visited: set[str] = set()
    for parent,dirs,files in os.walk(root, followlinks=True):
        try:
            real=os.path.realpath(parent)
        except OSError:
            unreadable.append(parent)
            dirs[:]=[];continue
        if real in visited:
            dirs[:]=[];continue
        visited.add(real)
        keep=[]
        for d in sorted(dirs):
            if d in SKIP_DIRS:continue
            if not os.access(os.path.join(parent,d), os.R_OK | os.X_OK):
                unreadable.append(os.path.join(parent,d));continue
            keep.append(d)
        dirs[:]=keep
        for item in sorted(files):
            walked+=1
            if walked > ceiling:
                return
            if item == name or (name=='*.jsonl' and item.endswith('.jsonl')):
                yield Path(parent)/item


def skill_header(text: str) -> dict[str,str]:
    """Parse only simple name/description/version fields; no YAML execution."""
    if not text.startswith('---'):
        return {}
    header=text.split('---',2)[1]
    result={}
    for key in ('name','description','version','edge-id','edge-version','edge-url'):
        m=re.search(r'^\s*'+key+r':\s*([^\n]+)',header,re.M)
        if m:result[key]=m.group(1).strip().strip('\"\'')[:1200]
    return result


#: Where a host agent keeps the executable that bundles its own skills.
HOST_BINARIES=(Path.home()/'.local/share/claude/versions',)


#: Roots under which a session is machine-made, not somebody working. Checked on
#: the resolved path so a symlinked temp dir cannot slip past.
TEMP_ROOTS=('/private/tmp/','/tmp/','/var/folders/','/private/var/folders/')


def is_harness_session(cwd: str | None, project: Path | None = None) -> bool:
    """Whether this session is an evaluation run rather than the user's work.

    SKILL.md requires it: "Exclude Brain Surgery/evaluation sessions from
    normal-usage evidence." It was never implemented, and the cost was 13 of 22
    findings on a real scan. The grid harness spawns agent children that load its
    synthetic `bs*` skills, those skills live in `eval/skills/` which is not a
    scanned root, and every one came back as "loaded but not found on disk". The
    scan was reporting its own test fixtures as faults in the user's setup.

    Keyed on the working directory, because an eval child runs in a throwaway
    workspace under the system temp root and a person's real work does not. That
    also catches any other harness using a temp workspace, without this file
    needing to know which harness it was.
    """
    if not cwd:
        return False
    try:
        resolved=Path(cwd).resolve()
    except OSError:
        return False
    # Scanning a project that happens to live under a temp root is a real thing to
    # do, and those sessions are in scope by the user's own choice. Only a temp
    # workspace *outside* what was scanned is machine-made.
    if project is not None:
        try:
            resolved.relative_to(Path(project).resolve())
            return False
        except ValueError:
            pass
    text=str(resolved)
    if not text.endswith('/'):
        text+='/'
    return text.startswith(TEMP_ROOTS)


def host_bundled(names: set[str]) -> set[str]:
    """Which of these names the host agent ships inside itself.

    A bundled skill loads perfectly and has no SKILL.md anywhere on disk, because
    it lives in the host executable. The scan saw 19 of those and reported every
    one as "loaded but was not found on disk", which reads as a fault in the user's
    setup and is nothing of the kind: `artifact-design`, `artifact-capabilities`
    and `dataviz` are all shipped by Claude Code itself.

    Detected by searching the host binary rather than by carrying a hard-coded
    list, so the answer follows the installed version instead of drifting from it.
    A name is only looked for once, and only when the scan already has a gap to
    explain, so the binary is read at most once per scan and never for a machine
    with nothing to check.
    """
    if not names:
        return set()
    found=set()
    for root in HOST_BINARIES:
        if not root.is_dir():continue
        versions=sorted((p for p in root.iterdir() if p.is_file()),
                        key=lambda p:p.stat().st_mtime,reverse=True)
        for binary in versions[:1]:
            try:
                blob=binary.read_bytes()
            except OSError:
                continue
            for name in names:
                # NUL-delimited in the string table, which avoids matching a name
                # that merely appears inside a longer identifier.
                if b'\x00'+name.encode()+b'\x00' in blob:
                    found.add(name)
            break
    return found


def inventory(roots: list[Path]) -> dict[str,Any]:
    result=[];warnings=[];seen=set()
    unreadable.clear()
    for root in roots:
        if not root.exists():
            warnings.append(f'Skill root not found: {root}')
            continue
        for p in bounded_files(root,'SKILL.md'):
            # A runaway guard, not a sampling knob. At 300 it bound on an ordinary
            # heavily-used machine and silently set the headline itself, which is
            # the same failure the session and byte caps above were raised for.
            if len(result)>=MAX_INVENTORY:
                warnings.append(f'{MAX_INVENTORY}-skill inventory limit reached; '
                                'counts below are a floor, not a ceiling')
                break
            if str(p.resolve()) in seen:continue
            seen.add(str(p.resolve()))
            if p.stat().st_size>262144:
                warnings.append(f'Skipped oversized SKILL.md: {p}')
                continue
            text=p.read_text(encoding='utf-8',errors='replace')
            h=skill_header(text)
            # Key on the directory name, because that is what the host uses to
            # address a skill, and record the declared name as an alias.
            #
            # These disagree more often than they look like they would: 13 of the
            # skills on one real machine declare a name different from their
            # directory. `~/.claude/skills/gstack-browse/SKILL.md` declares
            # `browse`. The transcript recorded a load of `gstack-browse`, the
            # inventory held it under `browse`, and the scan reported the same
            # skill twice: once as loaded-but-missing-from-disk, once as dormant.
            # One key mismatch, two findings, both wrong.
            declared=h.get('name')
            # Only the description is load-bearing, and not for loading.
            #
            # An earlier version flagged a missing `name` or missing frontmatter as
            # "cannot load". That is false, and it was checked the wrong way round:
            # `~/.claude/skills/chrome-cdp-skill/SKILL.md` has no frontmatter at all
            # and was invoked eight times through the Skill tool, because the host
            # addresses a skill by its directory name. A `name` field is optional
            # and its absence breaks nothing.
            #
            # A missing description is different and still worth saying. The
            # description is what the agent reads when deciding whether to open a
            # skill, so without one the skill can still be called by name and has
            # nothing for the agent to match a task against. That is the failure
            # TASK_SPEC.md names: how a good skill never gets reached.
            malformed=[] if h.get('description') else ['no description']
            result.append({
                'malformed':malformed or None,'local_id':hashlib.sha256(str(p.resolve()).encode()).hexdigest()[:16],
                'name':p.parent.name,
                'declared_name':declared if declared and declared!=p.parent.name else None,
                'aliases':sorted({a for a in (declared,p.parent.name) if a}),
                'description':h.get('description',''),
                'version':h.get('version'),'edge_id_claim':h.get('edge-id'),'edge_version_claim':h.get('edge-version'),'edge_url_claim':h.get('edge-url'),'path':str(p.resolve()),'skill_md_sha256':file_digest(p),
                'fingerprint_scope':'SKILL.md only; selected bundles need full manifest at freeze time',
                'full_content_loaded':False})
    if unreadable:
        warnings.append('Could not read %d path(s), so the inventory is a floor: %s'
                        % (len(unreadable), ', '.join(sorted(set(unreadable))[:5])))
    bad=[x for x in result if x.get('malformed')]
    if bad:
        warnings.append('%d SKILL.md file(s) are missing required frontmatter and may not '
                        'load at all: %s' % (len(bad), ', '.join(sorted(x['name'] for x in bad)[:5])))
    return {'skills':result,'warnings':warnings}


def content_text(content: Any) -> str:
    if isinstance(content,str):return content
    if isinstance(content,list):
        return '\n'.join(x.get('text','') for x in content if isinstance(x,dict) and x.get('type') in {'text','input_text','output_text'})
    return ''


def normalize(rows: list[dict[str,Any]], host: str, source: str) -> dict[str,Any]:
    """Recognizes common Claude/Codex JSONL shapes; not a universal parser.
    Calls mentioning skills are attempts. Only explicit matched successful
    Skill-tool results become confirmed loads. File-read inference is omitted.
    """
    cwd=None; turns=[];attempts={};loads=[];failures=[];recognized=0
    for i,row in enumerate(rows):
        if not isinstance(row,dict):continue
        if isinstance(row.get('cwd'),str):cwd=row['cwd']
        payload=row.get('payload',{})
        if row.get('type')=='session_meta' and isinstance(payload,dict):cwd=payload.get('cwd',cwd)
        if host=='claude':
            msg=row.get('message',{})
            if not isinstance(msg,dict):continue
            if row.get('type') not in {'user','assistant'}:continue
            recognized+=1; content=msg.get('content',[])
            text=content_text(content)
            if text:
                turns.append({'role':row['type'],'text':text[:3000],'event':i,'timestamp':row.get('timestamp'),'truncated':len(text)>3000})
            if isinstance(content,list):
                for part in content:
                    if not isinstance(part,dict):continue
                    if part.get('type')=='tool_use' and str(part.get('name','')).lower()=='skill':
                        args=part.get('input',{})
                        # Stamped per attempt, not per session. Attributing a
                        # session's last activity to every skill it ever touched
                        # makes a long-running session report every one of them as
                        # reached "now", which is how a skill last used days ago
                        # looked current.
                        if isinstance(args,dict):attempts[part.get('id')]= {'name':str(args.get('skill',''))[:120], 'event':i, 'at':row.get('timestamp')}
                    if part.get('type')=='tool_result' and part.get('tool_use_id') in attempts:
                        attempt=attempts[part['tool_use_id']]
                        # Success omits is_error entirely; only an explicit True is a
                        # failure. Requiring `is False` scored every real load as a zero.
                        # An attempt with no matched result stays in neither list: an
                        # unfinished trace is not a failure.
                        if part.get('is_error') is True:
                            failures.append({**attempt,'confirmation_event':i,
                                'evidence':'matched Skill-tool result flagged is_error'})
                        else:
                            loads.append({**attempt,'confirmation_event':i,
                                'evidence':'matched Skill-tool result without an error flag'})
        elif host=='codex':
            if row.get('type')!='response_item' or not isinstance(payload,dict):continue
            recognized+=1
            if payload.get('type')=='message' and payload.get('role') in {'user','assistant'}:
                text=content_text(payload.get('content',[]))
                if text:turns.append({'role':payload['role'],'text':text[:3000],'event':i,'timestamp':row.get('timestamp'),'truncated':len(text)>3000})
            # Codex has no Skill tool. A skill is loaded by the agent reading its
            # SKILL.md through the shell, so that read IS the invocation, and
            # without parsing it the scan reported every Codex skill as dormant:
            # 214 of 214 on a real machine, which is the false alarm this product
            # exists to avoid rather than produce.
            #
            # Only reads under a directory literally named `skills` count. Matching
            # any SKILL.md anywhere would count a person editing a skill file, or a
            # harness reading its own fixtures, as using the skill.
            if payload.get('type')=='custom_tool_call':
                blob=str(payload.get('input') or payload.get('arguments') or '')
                for m in CODEX_SKILL_READ.finditer(blob):
                    name=m.group('name')
                    key=f'{i}:{name}'
                    if key in attempts:continue
                    attempts[key]={'name':name,'event':i,'at':row.get('timestamp'),
                        'evidence':'SKILL.md read through the shell, which is how a '
                                   'Codex skill is loaded'}
                    # The read completing is the load. There is no separate result
                    # event to match, so a failed read shows up as a shell error and
                    # is not claimed either way.
                    loads.append({**attempts[key],'confirmation_event':i,
                        'evidence':'SKILL.md read through the shell'})
            if payload.get('type')=='function_call':
                name=str(payload.get('name','')); args=payload.get('arguments','')
                if 'skill' in name.lower() or 'SKILL.md' in str(args):
                    attempts[str(payload.get('call_id',i))]={'name':name,'event':i,'at':row.get('timestamp'),'arguments_excerpt':str(args)[:250]}
    # When this session was last active. Without it a skill that ran once weeks ago
    # and a skill failing right now are indistinguishable, and the scan reported both
    # as the same finding. Taken from the turns rather than the file's mtime, which
    # changes for reasons that have nothing to do with the conversation.
    stamps=[t['timestamp'] for t in turns if t.get('timestamp')]
    return {'source':source,'host':host,'cwd':cwd,'turns':turns,
        'last_activity':max(stamps) if stamps else None,
        'skill_attempts':list(attempts.values()),'confirmed_skill_loads':loads,
        'failed_skill_loads':failures,
        'invocation_coverage':'partial' if recognized else 'unrecognized',
        'absence_is_not_zero':True,'recognized_events':recognized,
        'grouping':'Host agent must group requests and corrections; these turns are not independent tasks.'}


def encode_project(project: Path) -> str:
    """Claude Code names a project's log directory after its path, with every
    separator replaced by a dash."""
    return str(project).replace('/','-')


def bare_skill_name(name: str | None) -> str:
    """A plugin skill loads under `plugin:skill` but names itself `skill` in its own
    SKILL.md. Strip the qualifier so the inventory and the transcripts agree on what
    a skill is called. Directory-scoped skills use the same separator, so this also
    covers `apps/web:deploy`."""
    if not name:return ''
    return name.rsplit(':',1)[-1].strip()


def default_skill_roots(project: Path, home: Path, host: str='claude') -> list[Path]:
    """Project-local skills first, then the user-level roots. Skills are usually
    installed once for the whole machine, so a project-only inventory misses most
    of them and makes the setup look far smaller than it is.

    Roots are per host. A machine that runs both Codex and Claude keeps a root for
    each, usually with the same skills copied into both, and pooling them counts
    every shared skill twice: once as installed capability the scanned host never
    reached, and once as a name declared in two places. Both readings are wrong,
    because the other host's root was never on this host's search path.

    Plugin roots do count. A plugin the user installed puts real, loadable skills
    under the plugin cache, and leaving that out reported skills that demonstrably
    load as missing from disk, which reads as a fault in the setup rather than a
    gap in this scan.
    """
    roots=[project/'.agents/skills', project/'.claude/skills', home/'.agents/skills']
    roots.append(home/('.codex/skills' if host=='codex' else '.claude/skills'))
    if host=='codex':
        return roots
    # Installed plugin versions only. The sibling `marketplaces/` tree is the
    # catalogue clone: it holds every plugin the marketplace offers, including ones
    # this machine never installed, and counting those as installed capability
    # inflates the denominator with skills the agent could never have reached.
    #
    # One version per plugin. The cache never evicts, so a plugin updated ten times
    # leaves ten version directories side by side. All but the newest are dead, and
    # counting them turns routine plugin updates into nine phantom installs and a
    # name-collision warning about a plugin that is in fact working fine.
    newest: dict[tuple[str,str],Path] = {}
    for skills in (home/'.claude/plugins/cache').glob('*/*/*/skills'):
        if not skills.is_dir():continue
        version=skills.parent
        key=(version.parent.parent.name, version.parent.name)   # marketplace, plugin
        current=newest.get(key)
        if current is None or version.stat().st_mtime > current.parent.stat().st_mtime:
            newest[key]=skills
    roots+=[newest[k] for k in sorted(newest)]
    return roots


def default_log_roots(host: str, project: Path, home: Path, scope: str) -> tuple[list[Path],list[str]]:
    """Where each host keeps its transcripts.

    Scope matters for honesty, not just for recall. Skills are installed for the
    whole machine, so 'never used' measured inside a single project would call a
    skill dormant that the user leans on elsewhere. 'user' scope reads recent
    sessions across projects; 'project' scope reads only this one and the report
    has to say so.
    """
    found: list[Path] = []
    notes: list[str] = []
    claude_projects = home/'.claude'/'projects'
    codex_sessions = home/'.codex'/'sessions'
    if host in ('claude','auto') and claude_projects.is_dir():
        if scope=='project':
            exact = claude_projects/encode_project(project)
            if exact.is_dir():
                found.append(exact)
            else:
                notes.append(f'No Claude transcripts for this project yet: {exact}')
        else:
            found.extend(sorted(d for d in claude_projects.iterdir() if d.is_dir()))
    if host in ('codex','auto') and codex_sessions.is_dir():
        found.append(codex_sessions)
    if not found:
        notes.append('No agent transcript directory found. Looked for '
                     f'{claude_projects} and {codex_sessions}.')
    return found, notes


def inspect(project: Path, host: str, roots: list[Path], logs: list[Path], days=90, max_sessions=500, explicit=False, scope='project') -> dict[str,Any]:
    project=project.resolve();now=datetime.now(timezone.utc)
    inv=inventory(roots);sessions=[];harness_sessions=[];warnings=inv['warnings'];budget=0
    cutoff=(now-timedelta(days=days)).timestamp()
    candidates=[]
    for root in logs:
        if root.is_file() and not root.is_symlink():candidates.append(root)
        elif root.is_dir():candidates.extend(bounded_files(root,'*.jsonl') or [])
        else:warnings.append(f'Log path not found: {root}')
    # A subagent transcript is a fragment of its parent session, not a session of
    # its own: it has no user prompt and shares the parent's work. Counting each
    # one as a session lets a single busy session crowd every other one out of the
    # window. Its skill events still count, merged into the parent below.
    candidates=sorted(set(candidates),key=lambda p:p.stat().st_mtime,reverse=True)
    helpers:dict[str,list[Path]]={}
    primaries=[]
    for p in candidates:
        if p.parent.name=='subagents':
            helpers.setdefault(p.parent.parent.name,[]).append(p)
        else:
            primaries.append(p)
    candidates=primaries
    for path in candidates:
        if len(sessions)>=max_sessions:break
        if path.stat().st_mtime<cutoff:continue
        if budget>=MAX_TOTAL_BYTES:
            warnings.append('Total transcript read budget exhausted');break
        # Stream line by line. Real transcripts run to tens of MB; refusing a whole
        # file on size silently drops the sessions that matter most. A single row is
        # bounded, the file is not.
        rows=[];bad=0;oversized=0
        with path.open('rb') as f:
            for line in f:
                budget+=len(line)
                if len(line)>MAX_LINE_BYTES:
                    oversized+=1;continue
                if len(rows)>=MAX_LOG_ROWS:
                    warnings.append(f'Row cap reached, log read is partial: {path}');bad+=1;break
                # ValueError, not JSONDecodeError. `json.loads` on bytes sniffs the
                # encoding first, so a binary file in the logs directory raises
                # UnicodeDecodeError, which is not a JSONDecodeError and escaped the
                # handler entirely. One stray binary file killed the whole scan.
                # Both subclass ValueError.
                try:rows.append(json.loads(line))
                except ValueError:bad+=1
        if oversized:
            warnings.append(f'Skipped {oversized} oversized row(s), invocation trace may be incomplete: {path}')
            bad+=oversized
        detected=host
        if detected=='auto':
            detected=detect_host(rows)
        item=normalize(rows,detected,str(path.resolve()))
        if scope=='project' and item['cwd'] and Path(item['cwd']).resolve()!=project:continue
        if not item['cwd'] and not explicit:
            warnings.append(f'Unknown project; skipped log: {path}');continue
        if any(marker in str(path) for marker in ('skill-forge/runs','brain-surgery/reports','brain-surgery/runs')):
            continue
        # Exclude explicit audit sessions, not arbitrary user conversations about skills.
        first_user=next((t['text'] for t in item['turns'] if t['role']=='user'),'')
        if first_user.lower().startswith(('run the installed brain surgery skill','/brain-surgery')):continue
        item['parse_errors']=bad
        if bad:item['invocation_coverage']='partial'
        # Fold in this session's subagent transcripts: their skill loads are real
        # loads, they just are not separate sessions.
        merged=0
        for helper in helpers.get(path.stem,[]):
            rows=[]
            with helper.open('rb') as f:
                for line in f:
                    budget+=len(line)
                    if len(line)>MAX_LINE_BYTES or len(rows)>=MAX_LOG_ROWS:continue
                    try:rows.append(json.loads(line))
                    except ValueError:item['parse_errors']=item.get('parse_errors',0)+1
            sub=normalize(rows,detected,str(helper.resolve()))
            for key in ('skill_attempts','confirmed_skill_loads','failed_skill_loads'):
                item[key]=item.get(key,[])+sub.get(key,[])
            merged+=1
        item['subagent_transcripts_merged']=merged
        # An evaluation run is not usage. Held aside and counted rather than
        # dropped silently, so a scan that excluded a lot can say so.
        if is_harness_session(item.get('cwd'), project):
            harness_sessions.append(item.get('source'))
            continue
        sessions.append(item)
    # A skill the agent actually loaded but the inventory never saw means a skill root
    # was missed. Report it; never let the inventory quietly contradict the transcripts.
    # A plugin skill is recorded as `plugin:skill` when it loads and as the bare name
    # in its own SKILL.md, so compare on the bare name or every plugin skill on the
    # machine reads as missing from disk.
    # Match on every name a skill answers to. A skill whose directory and declared
    # name differ is reachable under the directory name, and looking for only one of
    # the two reports a skill that is right there as missing from disk.
    known={bare_skill_name(a) for s in inv['skills'] for a in (s.get('aliases') or [])
           if a}
    used={a['name'] for x in sessions for a in x['skill_attempts'] if a.get('name')}
    unseen=sorted({bare_skill_name(n) for n in used if n and bare_skill_name(n) not in known})
    # A skill the host ships inside itself loads perfectly and has no SKILL.md to
    # find. Reporting that as a gap blames the user for the host's packaging.
    bundled=sorted(host_bundled(set(unseen)))
    unseen=[n for n in unseen if n not in bundled]
    # A gap only matters if the agent is still reaching for it. A skill that ran a
    # month ago and has not been tried since was removed, which is ordinary churn
    # and not a fault. The scan's own integration fixture proved the point: it ran
    # once in a disposable workspace, the workspace was deleted, and it was reported
    # as a skill missing from disk.
    recent_cut=(now-timedelta(days=STALE_GAP_DAYS)).isoformat()
    last_try={}
    for x in sessions:
        for a in x.get('skill_attempts',[]):
            n=bare_skill_name(a.get('name'))
            stamp=a.get('at')
            if n and stamp:last_try[n]=max(last_try.get(n,''),stamp)
    stale=sorted(n for n in unseen if n in last_try and last_try[n] < recent_cut)
    unseen=[n for n in unseen if n not in stale]
    if unseen:
        warnings.append('Loaded but not inventoried (a skill root is missing from --skill-root): '
                        +', '.join(unseen))
    # An empty scan is the one result that must never read as a clean bill of
    # health. Say plainly that nothing was read, so it cannot be mistaken for
    # "nothing is wrong".
    if not sessions:
        warnings.append('No transcripts were read, so nothing here is a measurement. '
                        'This is not evidence that your setup is healthy.')
    return {'schema_version':'brain-surgery-inspection/0.3','created_at':now.isoformat(),
        'host_bundled':bundled,'stale_gaps':stale,
        'harness_sessions_excluded':len(harness_sessions),
        'project':str(project),'host':host,'skills':inv['skills'],'sessions':sessions,
        'inventory_gap':unseen,'scope':scope,
        'limits':{'days':days,'max_sessions':max_sessions,'bytes_read':budget},
        'warnings':warnings,'privacy':'LOCAL ONLY. Contains private excerpts. Never publish this file.',
        'evaluation_performed':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('--host',choices=['auto','claude','codex'],default='auto')
    p.add_argument('--skill-root',type=Path,action='append',default=[]);p.add_argument('--logs',type=Path,action='append',default=[])
    p.add_argument('--days',type=int,default=90)
    # Exhaustive by default: a cap that truncates the history makes the headline
    # move with the cap instead of with the setup. A full pass is read-only and
    # takes seconds, so there is no reason to sample.
    p.add_argument('--max-sessions',type=int,default=500)
    p.add_argument('--explicit-log-scope',action='store_true',help='Authorize supplied logs even without project metadata')
    p.add_argument('--scope',choices=['project','user'],default='project',
        help='project: only this project\'s sessions. user: recent sessions across all projects, '
             'which is what "never used" needs since skills are installed machine-wide.')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not a.project.is_dir():p.error('Project directory does not exist')
    if not 1<=a.max_sessions<=2000 or not 1<=a.days<=365:p.error('Invalid scan limits')
    home=Path.home()
    roots=a.skill_root or default_skill_roots(a.project,home,a.host)
    logs=a.logs; notes=[]
    if not logs:
        logs,notes=default_log_roots(a.host,a.project,home,a.scope)
        # Discovered roots are the host's own directories, not a user-supplied path,
        # so their sessions are in scope by construction.
        a.explicit_log_scope=True
    try:
        result=inspect(a.project,a.host,roots,logs,a.days,a.max_sessions,a.explicit_log_scope,a.scope)
        result['warnings']=notes+result['warnings']
        result['log_roots']=[str(x) for x in logs]
        write_json(a.out,result)
    except (ValueError,OSError) as e:p.exit(2,f'Inspection failed: {e}\n')
    print(json.dumps({'skills':len(result['skills']),'sessions':len(result['sessions']),
        'warnings':len(result['warnings']),'scope':a.scope,'output':str(a.out),'uploaded':False}))
if __name__=='__main__':main()
