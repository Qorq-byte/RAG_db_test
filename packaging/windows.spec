# Build from repository root: python -m PyInstaller packaging/windows.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files('ragdb')
hidden = collect_submodules('ragdb')
# Chroma and keyring instantiate these implementations by import path.
for package in ['chromadb', 'keyring.backends']:
    hidden += collect_submodules(package)
for package in ['chromadb', 'sentence_transformers', 'transformers', 'tokenizers', 'tiktoken']:
    datas += collect_data_files(package)
for package in ['chromadb', 'sentence-transformers', 'transformers', 'torch', 'tqdm', 'regex',
                'requests', 'packaging', 'filelock', 'numpy', 'tokenizers', 'huggingface-hub',
                'safetensors', 'pyyaml', 'scikit-learn', 'scipy']:
    datas += copy_metadata(package)
a = Analysis([str(root / 'packaging/launcher.py')], pathex=[str(root / 'src')],
             datas=datas, hiddenimports=hidden, excludes=['pytest', 'IPython', 'matplotlib', 'tkinter'],
             noarchive=False)
# Qt6 on Windows uses the OS ICU API (unversioned symbols). A foreign ICU
# found through PATH, e.g. Poppler's *_78 build, shadows it and breaks QtCore.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RAGDB-CLI', console=True)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='RAGDB', console=False)
coll = COLLECT(cli, gui, a.binaries, a.datas, name='RAGDB')
