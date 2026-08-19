from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Questao(BaseModel):
    numero: int = Field(ge=1)
    option_count: int = Field(ge=2, le=5)
    resposta: str
    peso: float = Field(default=1.0, ge=0.1, le=1.0)

    @field_validator("resposta")
    @classmethod
    def resposta_em_maiusculo(cls, value: str) -> str:
        return value.strip().upper()


class AlunoParaFolha(BaseModel):
    aluno_id: str = Field(min_length=1)
    nome: str = Field(default="")
    matricula: str = Field(default="")


class GerarGabaritoRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    identificador: str = Field(default="")
    questoes: list[Questao] = Field(min_length=1, max_length=100)
    matricula_em_blocos: bool = True
    alunos: list[AlunoParaFolha] = Field(default_factory=list)
    turma: str = Field(default="")

    @field_validator("questoes")
    @classmethod
    def respostas_validas(cls, questoes: list[Questao]) -> list[Questao]:
        for questao in questoes:
            permitido = [chr(ord("A") + i) for i in range(questao.option_count)]
            if questao.resposta not in permitido:
                raise ValueError(
                    f"Resposta inválida na questão {questao.numero}: "
                    f"deve ser uma de {permitido}."
                )
        return questoes


class ArquivoGerado(BaseModel):
    template_json: dict[str, Any]
    config_json: dict[str, Any]
    marcador_base64: str
    folha_respostas_base64: str
    folha_solucao_base64: str


class FolhaAluno(BaseModel):
    aluno_id: str
    folha_base64: str


class GerarGabaritoResponse(BaseModel):
    gabarito: dict[str, str]
    pesos: dict[str, float]
    arquivos: ArquivoGerado
    folhas_alunos: list[FolhaAluno] = Field(default_factory=list)
    # Todas as folhas_alunos combinadas em um único PDF (uma página por
    # aluno, na mesma ordem) — None se não houver alunos.
    folha_completa_base64: str | None = None


class MatriculaDetectada(BaseModel):
    valor: str
    digitos: list[str]
    ink_ratios: list[float]
    gap_invalido: bool


class DetalheQuestao(BaseModel):
    questao: int
    selecionada: str
    resposta_correta: str
    correta: bool
    em_branco: bool
    peso: float
    valor_questao: float
    pontos_obtidos: float


class NotaCalculada(BaseModel):
    acertos: int
    erros: int
    em_branco: int
    total: int
    nota: float
    nota_maxima: float
    percentual: float
    peso_ganho: float
    peso_total: float
    detalhes: list[DetalheQuestao]


class QRDetectado(BaseModel):
    simulado_id: str
    aluno_id: str


class CorrigirFolhaResponse(BaseModel):
    respostas_detectadas: dict[str, str]
    matricula: MatriculaDetectada | None = None
    qr: QRDetectado | None = None
    nota: NotaCalculada | None = None
    imagem_processada_base64: str | None = None
    log_excerto: str = ""


class PaginaDividida(BaseModel):
    nome: str
    conteudo_base64: str


class DividirFolhaResponse(BaseModel):
    paginas: list[PaginaDividida]
