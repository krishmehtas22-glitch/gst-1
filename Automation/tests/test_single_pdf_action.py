"""ONE PDF cannot silently expand to a multiple-row selection or a client batch."""
import pytest

from test_manual_ai_queue import controller


@pytest.mark.parametrize('approved',[True,False])
def test_one_pdf_button_with_one_hundred_selected_rows_dispatches_only_focused_pdf(tmp_path,monkeypatch,approved):
    import Invoice_Desktop as gui
    from Common_Rules import desktop_ai
    app=controller(tmp_path,100)
    app.table.focus=lambda:'73'
    calls=[];prompts=[]
    class ImmediateThread:
        def __init__(self,target,**kwargs):self.target=target
        def start(self):self.target()
    monkeypatch.setattr(gui.threading,'Thread',ImmediateThread)
    monkeypatch.setattr(gui.messagebox,'askyesno',lambda title,text:prompts.append(text) or approved)
    def run(root,records,provider,*a,**kw):
        calls.append((records,provider))
        return [],dict(new_ai_attempts=1,xml_prepared=100)
    monkeypatch.setattr(desktop_ai,'analyse_paths',run)
    app.analyse_one_pdf()
    assert len(calls)==int(approved)
    assert 'exactly 1 selected PDFs' in prompts[0] and '73.pdf' in prompts[0]
    if approved:
        assert calls==[([app.records[73]],'Groq')]
        messages=[]
        while not app.events.empty():messages.append(app.events.get())
        final=[value for kind,value in messages if kind=='progress'][-1]
        assert '1 new AI attempts (maximum 1)' in final
        assert 'Other PDFs received no new AI requests' in final
        assert '100 client XML vouchers' in final
    else:assert not app.busy and app.events.empty()


def test_one_pdf_button_refuses_ambiguous_multiple_selection_without_focus(tmp_path,monkeypatch):
    import Invoice_Desktop as gui
    app=controller(tmp_path,100);app.table.focus=lambda:''
    notices=[]
    monkeypatch.setattr(gui.messagebox,'showinfo',lambda *a:notices.append(a))
    monkeypatch.setattr(gui.InvoiceApp,'analyse_selected',lambda *a,**kw:pytest.fail('Must not analyse an ambiguous selection'))
    app.analyse_one_pdf()
    assert notices and not app.busy


def test_one_pdf_button_accepts_only_selected_row_even_if_focus_is_stale(tmp_path,monkeypatch):
    app=controller(tmp_path,100);app.table.selection=lambda:('21',);app.table.focus=lambda:'30'
    dispatched=[];app.analyse_selected=lambda provider,records:dispatched.append(records)
    app.analyse_one_pdf()
    assert dispatched==[[app.records[21]]]


def test_single_pdf_real_workflow_requests_only_that_pdf_and_caps_at_one(tmp_path,monkeypatch):
    from test_ai_first_flow import sources,runner
    from Common_Rules import gemini_batch
    from Common_Rules.desktop_ai import analyse_paths
    records=sources(tmp_path);events=[]
    batch=runner(events,monkeypatch)
    monkeypatch.setattr(gemini_batch,'read_with_fallback',batch)
    rows,report=analyse_paths(tmp_path,[records[1]],'Groq',True,True,False)
    assert events==[('ai','Groq',records[1]['digest'])]
    assert report['new_ai_attempts']==report['new_ai_attempt_limit']==1
    assert report['xml_prepared']==len(rows)==3
    assert all(r['status']=='not_selected_for_new_ai' for r in report['sources'] if r['digest']!=records[1]['digest'])
