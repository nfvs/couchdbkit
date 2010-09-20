# -*- coding: utf-8 -
#
# This file is part of couchdbkit released under the MIT license. 
# See the NOTICE for more information.

import traceback


from couchdbkit.consumer.base import check_callable
from couchdbkit.consumer.sync import SyncConsumer
from couchdbkit.utils import json

import eventlet
from eventlet.greenthread import GreenThread
from eventlet import event

class ChangeConsumer(object):
    def __init__(self, db, callback, **params):
        self.process_change = callback
        self.params = params
        self.db = db
        self.stop_event = event.Event()

    def wait(self):
        _ = eventlet.spawn_n(self._run)
        self.stop_event.wait()

    def _run(self):

        while True:
            try:
                resp = self.db.res.get("_changes", **self.params)
                return self.consume(resp)
            except (SystemExit, KeyboardInterrupt):
                eventlet.sleep(5)
                break
            except:
                traceback.print_exc()
                eventlet.sleep(5)
                break
        self.stop_event.send(True)

    def consume(self, resp):
        raise NotImplementedError

class ContinuousChangeConsumer(ChangeConsumer):

    def consume(self, resp):
        with resp.body_stream() as body:
            while True:
                line = body.readline()
                if not line:
                    break
                if line.endswith("\r\n"):
                    line = line[:-2]
                else:
                    line = line[:-1]
                self.process_change(line)
            self.stop_event.send(True)


class LongPollChangeConsumer(ChangeConsumer):

    def consume(self, resp):
        with resp.body_stream() as body:
            buf = []
            while True:
                data = body.read()
                if not data:
                    break
                buf.append(data)
            change = "".join(buf)
            try:
                change = json.loads(change)
            except ValueError:
                pass 
            self.process_change(change)
            self.stop_event.send(True)


class EventletConsumer(SyncConsumer):
    def __init__(self, db):
        eventlet.monkey_patch(socket=True)
        super(EventletConsumer, self).__init__(db)

    def fetch(self, cb=None, **params):
        if cb is None:
            return super(EventletConsumer, self).wait_once(**params)
        resp = self.db.res.get("_changes", **params)
        eventlet.spawn_n(cb, resp.json_body)
        eventlet.sleep(0.1)
        
    def wait_once(self, cb=None, **params):
        if cb is None:
            return super(EventletConsumer, self).wait_once(**params)

        check_callable(cb)
        params.update({"feed": "longpoll"})
        consumer = LongPollChangeConsumer(self.db, callback=cb,
                **params)
        consumer.wait()

    def wait(self, cb, **params):
        params.update({"feed": "continuous"})
        consumer = ContinuousChangeConsumer(self.db, callback=cb, 
                **params)
        consumer.wait()

