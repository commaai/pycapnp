"""Application reflection cache bound to a retained schema declaration.

Pass the stable field descriptor or module, rather than its freshly created
.schema wrapper. The declaration pins its owning schema and distinguishes
versions with identical wire IDs. Each result has independent mutable containers.
"""
import json


class ReflectionCache:
    def __init__(self):
        self._json = {}

    def encoded(self, declaration):
        if declaration not in self._json:
            from openpilot.system.webrtc.schema import generate_struct
            self._json[declaration] = json.dumps(generate_struct(declaration.schema), separators=(',', ':'))
        return self._json[declaration]

    def generate_struct(self, declaration):
        return json.loads(self.encoded(declaration))
