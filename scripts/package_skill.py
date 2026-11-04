"""Produce a self-contained standard Skill archive; never upload or publish it."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def package(output=None):
    output = Path(output) if output else ROOT / 'dist' / 'briefmint-skill.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'skills' / 'briefmint' / 'SKILL.md', 'briefmint/SKILL.md')
        archive.write(ROOT / 'LICENSE', 'briefmint/LICENSE')
        archive.write(ROOT / 'examples' / 'launch.json', 'briefmint/examples/launch.json')
        archive.write(ROOT / 'requirements-real.txt', 'briefmint/requirements-real.txt')
        archive.write(ROOT / 'docs' / 'integration.md', 'briefmint/references/integration.md')
        for source in sorted((ROOT / 'briefmint').glob('*.py')):
            archive.write(source, 'briefmint/scripts/briefmint/' + source.name)
        archive.writestr('briefmint/scripts/run.py', 'from briefmint.__main__ import main\nraise SystemExit(main())\n')
    return output


if __name__ == '__main__':
    print(package())
