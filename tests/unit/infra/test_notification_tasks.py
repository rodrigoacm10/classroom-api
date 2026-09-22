from unittest.mock import MagicMock, patch

from infra.tasks.notification_tasks import send_push_notification, _chunk


class TestNotificationTasks:
    """
    Suíte de Testes: Celery Notification Tasks (infra/tasks/notification_tasks.py)
    Valida a execução assíncrona da task Celery e integração com Firebase Cloud Messaging (FCM).
    """

    def test_chunk_utility(self):
        """Deve dividir uma lista em sublistas menores respeitando o tamanho máximo especificado."""
        tokens = [f"token_{i}" for i in range(12)]
        chunks = _chunk(tokens, 5)
        assert len(chunks) == 3
        assert len(chunks[0]) == 5
        assert len(chunks[1]) == 5
        assert len(chunks[2]) == 2

    def test_send_push_notification_empty_tokens_returns_zero(self):
        """Deve retornar contagem zero de sucesso e falha imediatamente sem invocar a API do Firebase caso a lista de tokens esteja vazia."""
        with patch("firebase_admin.messaging.send_each_for_multicast") as mock_send:
            res = send_push_notification(
                title="Teste",
                body="Corpo",
                data={"type": "TEST"},
                fcm_tokens=[],
            )
            assert res == {"success_count": 0, "failure_count": 0}
            mock_send.assert_not_called()

    def test_send_push_notification_multicast_success(self):
        """Deve construir a MulticastMessage com alta prioridade no Android, TTL, payload APNS e despachar via SDK do Firebase."""
        mock_response = MagicMock()
        mock_response.success_count = 2
        mock_response.failure_count = 0
        mock_response.responses = []

        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_response) as mock_send:
            res = send_push_notification(
                title="📋 Chamada Aberta",
                body="Entre no app",
                data={"type": "ATTENDANCE_OPENED", "duration_minutes": "15"},
                fcm_tokens=["token_android", "token_ios"],
            )

            assert res["success_count"] == 2
            assert res["failure_count"] == 0
            mock_send.assert_called_once()

            # Verificar payload montado
            message = mock_send.call_args.args[0]
            assert message.notification.title == "📋 Chamada Aberta"
            assert message.notification.body == "Entre no app"
            assert message.tokens == ["token_android", "token_ios"]
            assert message.android.priority == "high"
            assert message.android.ttl == 15 * 60  # 15 min em segundos

    def test_send_push_notification_batch_chunks(self):
        """Deve fracionar o envio em lotes de no máximo 500 tokens por requisição para respeitar os limites do FCM."""
        # 550 tokens devem gerar 2 lotes (500 + 50)
        tokens = [f"token_{i}" for i in range(550)]

        mock_resp_1 = MagicMock(success_count=500, failure_count=0, responses=[])
        mock_resp_2 = MagicMock(success_count=50, failure_count=0, responses=[])

        with patch("firebase_admin.messaging.send_each_for_multicast", side_effect=[mock_resp_1, mock_resp_2]) as mock_send:
            res = send_push_notification(
                title="Aviso Geral",
                body="Notificação em massa",
                data={"type": "ANNOUNCEMENT"},
                fcm_tokens=tokens,
            )

            assert res["success_count"] == 550
            assert res["failure_count"] == 0
            assert mock_send.call_count == 2
            # Lote 1 com 500
            assert len(mock_send.call_args_list[0].args[0].tokens) == 500
            # Lote 2 com 50
            assert len(mock_send.call_args_list[1].args[0].tokens) == 50

    def test_send_push_notification_identifies_and_cleans_stale_tokens(self):
        """Deve identificar tokens inativos/desinstalados (UNREGISTERED/registration-token-not-registered) e acionar a remoção no banco de dados."""
        mock_resp = MagicMock()
        mock_resp.success_count = 1
        mock_resp.failure_count = 1

        failed_item = MagicMock()
        failed_item.success = False
        failed_item.exception = MagicMock(code="registration-token-not-registered")

        success_item = MagicMock()
        success_item.success = True

        mock_resp.responses = [success_item, failed_item]

        with patch("firebase_admin.messaging.send_each_for_multicast", return_value=mock_resp):
            with patch(
                "modules.notification.infra.repositories.fcm_token_sqlalchemy_repository.FCMTokenSQLAlchemyRepository.remove_by_tokens"
            ) as mock_remove:
                res = send_push_notification(
                    title="Aviso",
                    body="Mensagem",
                    data={},
                    fcm_tokens=["token_valid", "token_stale"],
                )

                assert res["success_count"] == 1
                assert res["failure_count"] == 1
                mock_remove.assert_called_once_with(["token_stale"])

