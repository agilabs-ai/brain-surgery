import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_adapter(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'adapters' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLAUDE = load_adapter('claude_adapter')
CODEX = load_adapter('codex_adapter')


class AdapterContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.base = {
            'protocol': 'brain-surgery-adapter/0.3',
            'model': 'pinned-model-id',
            'prompt': 'Produce output.txt',
            'context': 'Only this supplied context is permitted.',
            'instructions': 'No network or external actions.',
            'configuration': '{}',
            'workspace': str(self.workspace),
            'limits': {'seconds': 12},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_claude_propagates_model_context_instructions_and_noninteractive_permissions(self):
        event = {'type': 'result', 'usage': {'input_tokens': 4, 'output_tokens': 3}}
        proc = subprocess.CompletedProcess([], 0, json.dumps(event) + '\n', '')
        with patch.object(CLAUDE.subprocess, 'run', return_value=proc) as called:
            result = CLAUDE.run(dict(self.base))
        cmd = called.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--model') + 1], 'pinned-model-id')
        self.assertEqual(cmd[cmd.index('--append-system-prompt') + 1], self.base['instructions'])
        self.assertIn(self.base['context'], cmd[2])
        self.assertIn(self.base['prompt'], cmd[2])
        self.assertIn('--permission-prompts', cmd)
        self.assertIn('--no-session-persistence', cmd)
        self.assertEqual(Path(called.call_args.kwargs['cwd']), self.workspace.resolve())
        self.assertEqual(result['usage']['total_tokens'], 7)

    def test_codex_propagates_model_context_instructions_and_workspace_sandbox(self):
        proc = subprocess.CompletedProcess([], 0, 'work complete\ntokens used 19\n', '')
        with patch.object(CODEX.subprocess, 'run', return_value=proc) as called:
            result = CODEX.run(dict(self.base))
        cmd = called.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--model') + 1], 'pinned-model-id')
        self.assertEqual(cmd[cmd.index('--sandbox') + 1], 'workspace-write')
        self.assertIn('--ephemeral', cmd)
        self.assertIn(self.base['instructions'], cmd[-1])
        self.assertIn(self.base['context'], cmd[-1])
        self.assertIn(self.base['prompt'], cmd[-1])
        self.assertEqual(Path(called.call_args.kwargs['cwd']), self.workspace.resolve())
        self.assertEqual(result['usage']['total_tokens'], 19)

    def test_claude_rejects_unenforceable_token_limit_without_launching(self):
        request = dict(self.base, limits={'seconds': 12, 'max_total_tokens': 1000})
        with patch.object(CLAUDE.subprocess, 'run') as called:
            result = CLAUDE.run(request)
        called.assert_not_called()
        self.assertEqual(result['status'], 'infrastructure_error')
        self.assertEqual(result['usage']['total_tokens'], 0)

    def test_codex_rejects_unenforceable_token_limit_without_launching(self):
        request = dict(self.base, limits={'seconds': 12, 'max_total_tokens': 1000})
        with patch.object(CODEX.subprocess, 'run') as called:
            result = CODEX.run(request)
        called.assert_not_called()
        self.assertEqual(result['status'], 'infrastructure_error')
        self.assertEqual(result['usage']['total_tokens'], 0)

    def test_candidate_bundle_copies_nested_files_and_rejects_path_names(self):
        source = self.workspace / 'source'
        (source / 'references').mkdir(parents=True)
        (source / 'SKILL.md').write_text('skill')
        (source / 'references' / 'guide.md').write_text('guide')
        target = self.workspace / 'target'
        target.mkdir()
        config = {'skill': {'name': 'safe-skill', 'source': str(source)}}
        CLAUDE.place_candidate(target, config)
        self.assertEqual((target / '.claude/skills/safe-skill/references/guide.md').read_text(), 'guide')
        with self.assertRaises(ValueError):
            CODEX.place_candidate(target, {'skill': {'name': '../escape', 'source': str(source)}})

    def test_timeout_is_infrastructure_and_preserves_pinned_model(self):
        for adapter in (CLAUDE, CODEX):
            with self.subTest(adapter=adapter.__name__), patch.object(
                    adapter.subprocess, 'run', side_effect=subprocess.TimeoutExpired([], 12)):
                result = adapter.run(dict(self.base))
                self.assertEqual(result['status'], 'infrastructure_error')
                self.assertEqual(result['model'], 'pinned-model-id')
                self.assertFalse(result['invocation']['complete'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
