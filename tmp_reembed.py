import json
from core.reembed import reembed_user
print(json.dumps(reembed_user('dd1d2ada-2514-4f9f-98ad-6fb3e0b93dbd', only_doc_id=20), indent=2))
