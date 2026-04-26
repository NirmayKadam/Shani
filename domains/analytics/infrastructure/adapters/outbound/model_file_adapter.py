from domains.analytics.application.ports.interface.outbound.i_model_store import i_model_store

class model_file_adapter(i_model_store):
    def save_model(self, symbol: str, path: str) -> None: pass
    def load_model(self, symbol: str) -> str: return ""
