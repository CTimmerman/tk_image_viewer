pip install -r requirements-dev.txt
pre-commit install
REM python -c "print('''#!/bin/env python\nimport re, sys; pat = '^(bug|feat)';\nif re.match(pat, open(sys.argv[1], 'r').read()): sys.exit(0)\nelse: print(f'Commit message doesn\\'t match {pat}'); sys.exit(1)''')" > .git/hooks/commit-msg
