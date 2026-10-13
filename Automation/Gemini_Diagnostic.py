"""Check local Gemini model access without uploading invoices or showing keys."""
import os
from pathlib import Path
from Common_Rules.gemini_reader import api_json,configured_model,DEFAULT_MODEL


def diagnose(transport=api_json):
    lines=['Gemini connection diagnostic — no invoice is uploaded']
    key=os.environ.get('GEMINI_API_KEY','').strip()
    lines.append('GEMINI_API_KEY present: '+('yes (hidden)' if key else 'no'))
    if not key:return lines+['Save the key privately in Windows User variables and reopen this diagnostic.']
    try:model=configured_model()
    except ValueError as exc:return lines+[str(exc)]
    lines.append('Model used: '+model)
    models=[];token=None
    try:
        for _ in range(3):
            from urllib.parse import quote
            path='models?pageSize=1000'+('&pageToken='+quote(token,safe='') if token else '')
            data=transport(path,key,timeout=15)
            models.extend(m.get('name','').removeprefix('models/') for m in data.get('models',[]) if 'generateContent' in m.get('supportedGenerationMethods',[]))
            token=data.get('nextPageToken')
            if not token:break
    except ValueError as exc:return lines+['Model-list request failed: '+str(exc)]
    lines.append('Model-list request: succeeded')
    lines.append('Configured model listed for generateContent: '+('yes' if model in models else 'no'))
    if model not in models:
        lines.append('Available generateContent IDs (PDF support not verified):')
        lines.extend('  '+name for name in models[:30] if name.startswith('gemini-'))
        return lines+['Choose a listed PDF-capable model; this diagnostic has not changed your model or billing settings.']
    payload={'contents':[{'parts':[{'text':'Reply only OK.'}]}],
             'generationConfig':{'temperature':0,'maxOutputTokens':64}}
    if model==DEFAULT_MODEL:payload['generationConfig']['thinkingConfig']={'thinkingBudget':0}
    try:
        result=transport('models/'+model+':generateContent',key,payload,timeout=25)
    except ValueError as exc:return lines+['Small text-generation request failed: '+str(exc)]
    choices=result.get('candidates',[])
    complete=bool(choices and choices[0].get('finishReason')=='STOP')
    lines.append('Small text-generation request: '+('succeeded' if complete else 'returned no complete candidate'))
    lines.append('A text success verifies model access; it does not verify PDF extraction accuracy.')
    return lines


if __name__=='__main__':
    print('Program folder:',Path(__file__).resolve().parent)
    print('\n'.join(diagnose()))
    print('The diagnostic does not print the API key. Share these result lines, not your environment-variable values.')
