"""Check Groq model access without uploading an invoice or printing keys."""
import os
from Common_Rules.groq_reader import api_json,configured_model


def diagnose(transport=api_json):
    key=os.environ.get('GROQ_API_KEY','').strip()
    lines=['Groq diagnostic — no invoice uploaded','GROQ_API_KEY present: '+('yes (hidden)' if key else 'no')]
    if not key:return lines+['Set GROQ_API_KEY privately in Windows User environment variables and reopen the app.']
    stage='configuration'
    try:
        model=configured_model();lines.append('Model used: '+model)
        stage='model-list request (no invoice)'
        data=transport('models',key,timeout=20)
        models=[m['id'] for m in data.get('data',[]) if isinstance(m,dict) and isinstance(m.get('id'),str) and m.get('active',True)]
        lines.append('Model-list request: succeeded')
        if model not in models:
            return lines+['Configured model not listed. Set GROQ_INVOICE_MODEL to a suitable listed text/chat model.']+models[:40]
        payload={'model':model,'messages':[{'role':'user','content':'Return JSON only: {"ok":true}'}],
                 'temperature':0,'max_completion_tokens':64,'response_format':{'type':'json_object'}}
        stage='small JSON generation request (no invoice)'
        response=transport('chat/completions',key,payload,timeout=30)
        choices=response.get('choices',[])
        complete=bool(choices and choices[0].get('finish_reason')=='stop')
        lines.append('Small JSON text request: '+('succeeded' if complete else 'no complete response'))
        lines.append('This verifies API access, not invoice accuracy. Check your Groq console for free-tier request/token limits.')
    except (ValueError,KeyError,TypeError) as exc:lines.append('Failed at '+stage+': '+str(exc))
    return lines


if __name__=='__main__':
    print('\n'.join(diagnose()))
    print('Share these result lines only; never share API keys.')
