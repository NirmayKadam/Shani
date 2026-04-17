from domains.analytics.ports.outbound.IModelStore import IModelStore

class ModelFileAdapter(IModelStore):
    def save_model(self, symbol: str, path: str) -> None: pass
    def load_model(self, symbol: str) -> str: return ""
