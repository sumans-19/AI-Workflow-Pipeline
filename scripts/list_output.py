import os
from pathlib import Path
print('cwd:', os.getcwd())
root = Path('output')
print('output exists:', root.exists())
for p in sorted(root.rglob('*')):
    print(p)
