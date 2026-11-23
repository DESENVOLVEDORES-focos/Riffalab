# Ajuste para busca de capas — RiffLab 0.6.9

Quando o iTunes retorna um álbum e um single da mesma música com a mesma URL de arte, o app agora conserva a informação do single para avaliação; antes o álbum podia vir primeiro e fazer o single ser descartado. A imagem ainda precisa passar pela verificação e pela revisão do usuário. Um álbum sozinho não é usado como single.

Se nenhuma capa for aprovada, a janela informa quantos candidatos foram descartados por falta de confirmação de single e quantos por imagem ou correspondência, quando houver essa informação. Sem candidatos, a mensagem recomenda conferir os erros das fontes. Essas contagens não identificam todas as causas; um serviço pode não responder ou não ter o single.

Nenhum MP3 existente é alterado, nem os parâmetros de download. Para atualizar, aguarde o lote, faça backup de `rifflab.db` e `config.json`, feche o app e mescle o ZIP, sem excluir banco, cookies, músicas, configurações, ferramentas ou `.venv`. Busque novamente a capa apenas nas músicas que deseja preparar.
