"""Run unchanged checks; surface failures as public Actions annotations, not just logs."""
from pathlib import Path
import os
import subprocess
import sys
import xml.etree.ElementTree as ET


def main():
    report=Path('Windows_Tests.xml')
    result=subprocess.run([sys.executable,'-m','pytest',*sys.argv[1:],'--junitxml='+str(report)])
    if result.returncode and report.exists():
        failures=[]
        for case in ET.parse(report).findall('.//testcase'):
            error=case.find('failure')
            if error is None:error=case.find('error')
            if error is None:continue
            name=case.get('name','Windows test');detail=(error.text or error.get('message',''))[:6000]
            encoded=detail.replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print('::error title=Windows regression '+name+'::'+encoded,flush=True)
            failures.append('### '+name+'\n```text\n'+detail+'\n```\n')
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary and failures:
            with Path(summary).open('a',encoding='utf-8') as stream:stream.write('## Windows regression diagnostics\n'+''.join(failures))
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
