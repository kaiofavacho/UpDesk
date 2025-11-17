document.addEventListener('DOMContentLoaded', function() {
    const chatContainer = document.querySelector('.chat-container');
    if (!chatContainer) return;

    const chamadoId = chatContainer.dataset.chamadoId;
    const currentUserId = parseInt(chatContainer.dataset.userId, 10);
    const chatMessages = document.getElementById('chat-messages');
    const form = document.getElementById('form-enviar-mensagem');
    const input = document.getElementById('input-mensagem');

    // Rola sempre pro fim
    function scrollChatToBottom() {
        if (!chatMessages) return;
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Renderiza UMA mensagem
    function renderizarMensagem(msg) {
        const row = document.createElement('div');
        const meta = document.createElement('div');
        const bubble = document.createElement('div');

        row.classList.add('chat-row');

        // se for o usuário logado -> direita, senão -> esquerda
        if (msg.usuario_id === currentUserId) {
            row.classList.add('me');
        } else {
            row.classList.add('them');
        }

        meta.className = 'chat-meta';
        meta.textContent = `${msg.usuario_nome} • ${msg.data_criacao}`;

        bubble.className = 'chat-bubble';
        bubble.textContent = msg.mensagem;

        row.appendChild(meta);
        row.appendChild(bubble);
        chatMessages.appendChild(row);
    }

    // Carrega TODAS as mensagens do chamado
    async function carregarMensagens() {
        try {
            const resp = await fetch(`/chamados/api/${chamadoId}/mensagens`);
            if (!resp.ok) {
                console.error('Falha ao carregar mensagens. Status:', resp.status);
                return;
            }

            const mensagens = await resp.json();

            chatMessages.innerHTML = '';

            if (!mensagens || mensagens.length === 0) {
                chatMessages.innerHTML = '<p class="text-center text-muted">Nenhuma mensagem ainda. Inicie a conversa!</p>';
            } else {
                mensagens.forEach(renderizarMensagem);
            }

            scrollChatToBottom();
        } catch (err) {
            console.error('Erro ao carregar mensagens:', err);
            chatMessages.innerHTML = '<p class="text-center text-danger">Erro ao carregar o chat.</p>';
        }
    }

    // Envia mensagem NOVA
    async function enviarMensagem(e) {
        e.preventDefault();

        const mensagemTexto = input.value.trim();
        if (!mensagemTexto) return;

        try {
            const resp = await fetch(`/chamados/api/${chamadoId}/mensagens`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ mensagem: mensagemTexto }),
            });

            if (!resp.ok) {
                console.error('Erro ao enviar mensagem. Status:', resp.status);
                alert('Erro ao enviar mensagem.');
                return;
            }

            input.value = '';
            await carregarMensagens();
        } catch (err) {
            console.error('Erro ao enviar mensagem:', err);
            alert('Erro ao enviar mensagem (ver console).');
        }
    }

    if (form) {
        form.addEventListener('submit', enviarMensagem);
    }

    if (chamadoId) {
        carregarMensagens();
        setInterval(carregarMensagens, 5000);
    }
});
