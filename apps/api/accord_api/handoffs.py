"""Create a bounded handoff without copying the source's private chat history."""
import json

from fastapi import HTTPException

from . import access, commands, context, store


def create(db, uid, target, title, body, refs=None, round_id=''):
    if target == uid or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (target,)).fetchone():
        raise HTTPException(422, '请选择需要接手的同事。')
    if round_id:
        access.round_for(db, target, round_id)
    checked = context.expand(db, uid, {'owner_id': uid, 'target_id': target, 'kind': 'peer', 'purpose': 'ordinary'}, refs or [])
    tid, now = store.new_id('thread'), store.now()
    db.execute('''INSERT INTO accord_threads(id,owner_id,target_id,title,kind,status,handoff_note,created_at,updated_at)
        VALUES(?,?,?,?,?,'waiting',?,?,?)''', (tid, uid, target, title, 'peer', title, now, now))
    if round_id:
        db.execute('INSERT INTO accord_thread_scopes VALUES(?,?,?)', (tid, 'handoff', round_id))
    commands.message(db, tid, 'human', uid, body, [r['id'] for r in checked], {'citations': checked})
    commands.message(db, tid, 'system', uid, '已交给本人，等待确认下一步。')
    return tid
