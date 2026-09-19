# Notes from the sync, 17 Sep

Rough, someone tidy this up.

- The importer keeps timing out on files over 200 MB. Ana said she would split the
  upload into chunks. Not started yet.
- Kim already rewrote the retry logic and merged it on Monday. That one is finished.
- Raul is waiting on the storage quota bump before he can move the nightly job off
  the shared box. Nothing he can do until that lands.
- Ana is partway through the config cleanup, roughly half the files migrated so far.
- Nobody has written the runbook for the failover drill. Kim picked it up at the end
  of the call.
- Raul to add the metrics endpoint so we can actually see the queue depth. Not
  started.

Open question: do we want a second reviewer on the importer change?
