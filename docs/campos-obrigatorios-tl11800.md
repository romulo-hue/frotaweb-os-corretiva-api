# Campos obrigatorios - TL11800

Com base na tela marcada pelo usuario, o lancamento minimo da OS corretiva deve
preencher apenas:

- Veiculo: `txtcd_veiculo`
- Entrada Data/Hora: `txtdh_entrada`
- Entrada Horimetro: `txtqt_hr_ent`
- Entrada Km: `txtqt_km_ent`
- Saida Data/Hora: `txtdh_saida`
- Saida Horimetro: `txtqt_hr_sai`
- Saida Km: `txtqt_km_sai`
- Data Prevista para Inicio: `txtdh_inicio`
- Data Prevista de Liberacao: `txtdh_prev`
- Horas Previstas: `txtqt_hr_prev`

O campo `txtnr_ordserv` nao deve ser enviado com valor no payload de entrada:
o FrotaWeb deve gerar a O.S. ao salvar.

Campos como placa, km atual/acumulado, filial e departamento sao derivados pelo
FrotaWeb a partir do veiculo ou preenchidos no proprio fluxo da tela.

O campo `txtnm_observ` e opcional no lancamento minimo. Quando usado, respeitar
o limite da propria tela: `maxlength=50`. Enviar texto maior bypassando o
navegador faz o FrotaWeb retornar erro IIS/OLE ao salvar.

Quando a API HTTP nao consegue fazer o FrotaWeb preencher esses derivados, o
payload pode informar os valores ja conhecidos:

- Placa: `txtplaca`
- Filial: `txtcd_filial`
- Departamento: `txtcd_ccusto`
- Filial oculta do veiculo: `hidcd_filialVeic`
- Departamento oculto do veiculo: `hidcd_ccustoveic`
- Trava de OS: `hidbl_trava_os`

## Fluxo tecnico

No navegador, ao preencher o veiculo, a tela executa um submit intermediario:

```text
Telas/TL11800.asp?acao=cd_veiculo
```

Depois disso, a tela tambem valida a entrada e a saida:

```text
Telas/TL11800.asp?acao=dh_entrada
Telas/TL11800.asp?acao=dh_saida
```

Esses passos sao necessarios antes do `Salvar`, pois populam campos ocultos e
campos derivados do veiculo. Sem eles, o FrotaWeb retorna erro IIS de tipo
incompativel por receber strings vazias em campos derivados.

Na captura CDP do veiculo `1830`, o FrotaWeb derivou:

- `hidcd_filialVeic = 4`
- `hidcd_ccustoveic = 420115`
- `hidnm_ccusto = PRECV - 002 BA - OPE MUNCKS`
- `hidbl_km = 1`
- `hidbl_hr = 0`
- `hidbl_medprop = 1`
- `hidqt_km_med = 5`
- `hidqt_km_acum = 3`
- `hiddh_ult_med = 20/03/2026 09:00:00`

## Teste real confirmado

Em 28/04/2026, o salvamento real pelo Chrome/CDP com payload minimo corrigido
gerou a O.S. `64805` para o veiculo `1830`/placa `THP2B33`.

Artefatos locais:

- HAR do salvamento: `artifacts/tl11800_submit_20260428_141638.har.json`
- HTML retornado: `artifacts/tl11800_submit_20260428_141638.html`
