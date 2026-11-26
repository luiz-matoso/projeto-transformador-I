# Validade temporal das observações

A validação entra em `ml.pipeline.apply_profile`, antes do motor de mobilidade.
Isso cobre tanto `infer_transitability` quanto a reaplicação de perfis sobre
uma cena já processada. O motor puro continua independente da data.

O prazo inicial é **24 horas**, apenas para demonstração: permite demonstrar
o vencimento em um ciclo diário e evita validade indefinida para uma cena urbana
mutável. Não é um prazo estabelecido pelo professor nem validado empiricamente.
Não há garantia de que as condições permaneçam iguais durante essas 24 horas.
O chamador configura `validity_period=timedelta(...)`, sem editar as regras.

```python
from datetime import timedelta
from ml.pipeline import infer_transitability
from ml.mobility_profile import MobilityProfile

result = infer_transitability(
    "caminho/trecho.png",
    MobilityProfile("adequate", "minor_problems", "minor", True),
    observation={"source": "vistoria_local", "observed_at": "2026-11-26T10:00:00-03:00"},
    validity_period=timedelta(hours=24),
)
```

`observed_at` é a data/hora em que o trecho foi observado/capturado, informada
pela origem da observação. Aceita datetime com fuso ou ISO 8601 com offset/Z.
Não é preenchida pela data do arquivo, upload, anotação ou processamento.
Sem uma data de captura/observação conhecida, o resultado é `undetermined`.
Datas sem fuso são inválidas. A avaliação usa UTC; `evaluated_at` permite uma
referência controlada para testes e simulações. Em produção, omita esse parâmetro.

A validade é o intervalo `[observed_at, expires_at)`: no instante exato do
vencimento, a observação já está vencida. Datas futuras são rejeitadas.
Origem ausente também impede avaliação. Prazo não positivo é erro de configuração.

O resultado contém `observation` com origem, data observada, prazo em segundos,
expiração, instante da avaliação, `is_valid`, código e mensagem. Observação
inválida/vencida retorna `undetermined`, severidade `none` (nenhuma severidade
de mobilidade foi avaliada), revisão necessária e motivo temporal. O motor não
é chamado, mesmo que as features existentes indiquem condição crítica. Features
e probabilidades podem continuar no resultado como diagnóstico, sem sustentar
uma afirmação de transitabilidade.

As quatro classificações de mobilidade permanecem iguais para observações válidas.
Chamadas antigas sem metadados agora retornam `undetermined`; essa mudança é
intencional. Os resultados históricos já gerados não foram reescritos. O script
de avaliação histórica dos 29 casos não conhece a data real de captura e, se
reexecutado sem metadados verificáveis, terá resultados temporais indeterminados.

## Cenário de defesa

Execute `python -m scripts.demo_observation_validity` na raiz do repositório.
O script reutiliza previsões reais registradas de
`curb_ramp/gsv-amsterdam-18384-CurbRamp.png`, sem nova inferência. A data de
captura real não é conhecida: os horários são explicitamente simulados.

Observação simulada: 26/11/2026 10:00 UTC. Avaliação inicial: 11:00 UTC.
- Perfil que requer piso regular: `non_transitable`, piso incompatível.
- Perfil que tolera problemas menores: `partially_transitable`, dificuldade moderada.
- Avaliação em 27/11/2026 às 11:00 UTC: `undetermined` para ambos, observação vencida.

Evidência: `artifacts/pipeline-evaluation/temporal-validity-demo/results.json`,
com perfis, datas, origem, features, classificações e motivos completos.
