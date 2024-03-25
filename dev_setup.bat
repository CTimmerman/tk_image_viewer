pip install -r requirements-dev.txt
pre-commit install
python -c "print('''#!/bin/env python\nimport re, sys; sys.exit(0 if re.match('^(bug|feat)', open(sys.argv[1], 'r').read()) else 1)''')" > .git/hooks/commit-msg
