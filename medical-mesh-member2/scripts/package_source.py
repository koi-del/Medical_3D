"""Bundle complete first-party source and public data; verify every archive entry."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('medical-mesh-member2')
EXCLUDED = {'__pycache__', '.pytest_cache', '.DS_Store'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries = {}

    def add(source, relative):
        if source.is_file():
            entries[(PREFIX / relative).as_posix()] = source

    for folder in ('src', 'scripts', 'tests', 'configs', 'docs', 'data/public'):
        for source in (ROOT / folder).rglob('*'):
            relative = source.relative_to(ROOT)
            if (any(p in EXCLUDED or p.endswith('.egg-info') for p in relative.parts)
                    or source.suffix == '.pyc' or '.local.' in source.name
                    or source.name.endswith('.partial')):
                continue
            add(source, relative)
    for name in ('.gitignore', 'README.md', 'THIRD_PARTY_NOTICES.md', 'pyproject.toml',
                 'requirements.in', 'requirements-lock-macos-arm64-py312.txt', 'run',
                 '启动医学网格工作台.command', '启动髌骨答辩演示.command'):
        add(ROOT / name, Path(name))
    for name in ('医学三维模型修复与格式适配_课程设计完整实施方案.md',
                 '成员2_医学三维模型优化评价与格式转换完整实施方案.md'):
        add(ROOT.parent / 'outputs' / name, Path('docs/plans') / name)
    add(ROOT / 'docs/source_bundle.md', Path('先读我_源码安装与运行.md'))
    expected_python = {p.relative_to(ROOT).as_posix()
                       for folder in ('src', 'scripts', 'tests')
                       for p in (ROOT / folder).rglob('*.py')
                       if '__pycache__' not in p.parts}
    bundled_python = {str(Path(name).relative_to(PREFIX))
                      for name in entries if name.endswith('.py')}
    if expected_python != bundled_python:
        raise RuntimeError('Source coverage mismatch')
    for name in expected_python:
        compile((ROOT / name).read_bytes(), name, 'exec')
    manifest = []
    temporary = destination.with_suffix('.partial.zip')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, source in sorted(entries.items()):
            data = source.read_bytes()
            info = zipfile.ZipInfo.from_file(source, name)
            # Finder-hidden flags belong to the source machine, not the delivery.
            info.external_attr = (source.stat().st_mode & 0xFFFF) << 16
            info.compress_type = (zipfile.ZIP_STORED if source.suffix == '.zip'
                                  else zipfile.ZIP_DEFLATED)
            archive.writestr(info, data)
            manifest.append({'path': name, 'bytes': len(data),
                             'sha256': hashlib.sha256(data).hexdigest()})
        archive.writestr((PREFIX / 'BUNDLE_MANIFEST.json').as_posix(),
                         json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise RuntimeError('ZIP integrity test failed')
        for row in manifest:
            data = archive.read(row['path'])
            if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                raise RuntimeError('Hash mismatch: ' + row['path'])
    temporary.replace(destination)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.zip.sha256').write_text(
        f'{digest}  {destination.name}\n', encoding='utf-8')
    print(json.dumps({'package': str(destination), 'files': len(manifest) + 1,
                      'python_files': len(expected_python), 'bytes': destination.stat().st_size,
                      'sha256': digest, 'integrity': 'passed'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
