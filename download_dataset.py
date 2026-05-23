import kagglehub
import shutil
from pathlib import Path

# baixa dataset
path = kagglehub.dataset_download("tobennao/rym-top-5000")

# pasta destino no projeto atual
destino = Path("./rym-top-5000")

# copia arquivos
shutil.copytree(path, destino, dirs_exist_ok=True)

print("Dataset copiado para:", destino.resolve())