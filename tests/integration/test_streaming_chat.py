"""A real delayed HTTP stream must paint before the response finishes."""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ragdb.application.chat import AnswerService
from ragdb.desktop.chat_page import ChatPage
from ragdb.domain.models import Collection, SearchHit
from ragdb.infrastructure.chat.openai_compatible import OpenAICompatibleChatModel
from ragdb.infrastructure.database import SQLiteDatabase, SQLiteCollectionRepository, SQLiteConversationRepository


APP = QApplication.instance() or QApplication([])


def test_real_http_stream_paints_before_completion_and_restores_history(tmp_path):
    release = Event()
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.end_headers()
            def send(value):
                self.wfile.write(('data: ' + value + '\n\n').encode('utf-8'))
                self.wfile.flush()
            send(json.dumps({'choices': [{'delta': {'content': '实时首段'}}]}, ensure_ascii=False))
            if release.wait(8):
                send(json.dumps({'choices': [{'delta': {'content': '，完整回答 [1]'}}]}, ensure_ascii=False))
                send('[DONE]')
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    database = SQLiteDatabase(tmp_path / 'library.sqlite3')
    database.initialize()
    collection = SQLiteCollectionRepository(database).create(Collection(name='synthetic'))
    repository = SQLiteConversationRepository(database)
    hit = SearchHit(rank=1, chunk_id='a', source_id=uuid4(), source_title='测试资料', source_uri='manual://test',
                    source_generation=1, text='合成资料', routes=('hybrid',))
    search = SimpleNamespace(search=lambda *_: [hit])
    def service():
        model = OpenAICompatibleChatModel('synthetic', f'http://127.0.0.1:{server.server_port}', 'synthetic-key', 5)
        return AnswerService(search, model, repository, evidence_limit=6, evidence_character_budget=1000, history_character_budget=500)
    runtime = SimpleNamespace(answer_service=service, conversations=repository)
    page = ChatPage(runtime)
    page.set_collection(collection.id, 'synthetic', 1)
    page.show()
    def until(predicate):
        deadline = time.monotonic() + 7
        while not predicate() and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(.005)
        assert predicate()
    try:
        page.question.setPlainText('测试实时回答')
        page.ask()
        until(lambda: '实时首段' in page.transcript.toPlainText())
        assert page.busy and not release.is_set()
        assert not repository.list_for_collection(collection.id)
        release.set()
        until(lambda: not page.busy)
        session_id = page.session_id
        assert requests[0][0] == '/chat/completions'
        assert requests[0][1]['stream'] is True
        assert repository.list_messages(session_id)[1].content == '实时首段，完整回答 [1]'
        reopened = ChatPage(runtime)
        reopened.set_collection(collection.id, 'synthetic', 1)
        reopened.sessions.setCurrentIndex(1)
        assert reopened.session_id == session_id
        assert reopened.transcript.messages[-1]._citations == '[1] 测试资料\nmanual://test'
        reopened.close()
    finally:
        release.set()
        if page.busy:
            page.cancel()
            until(lambda: not page.busy)
        page.close()
        server.shutdown()
        server.server_close()
        thread.join(2)
