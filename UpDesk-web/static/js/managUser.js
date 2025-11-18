// static/js/managUser.js
console.log('managUser.js carregado');

// -------------------------------------------------------------------
// FUNÇÕES GLOBAIS PARA OS BOTÕES (usadas no onclick do HTML)
// -------------------------------------------------------------------

// Abrir modal de criação
window.openCreateUserModal = function (event) {
  if (event) event.preventDefault();

  const modalEl = document.getElementById('modalCriarUsuario');
  if (!modalEl) {
    console.warn('modalCriarUsuario não encontrado');
    return;
  }

  if (window.bootstrap && bootstrap.Modal) {
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  } else {
    modalEl.classList.add('show');
    modalEl.style.display = 'block';
    modalEl.removeAttribute('aria-hidden');
  }
};

// Abrir modal de edição (chamado pelo botão de editar)
window.openEditUserModal = function (button) {
  if (!button) return;

  const IDtoEdit = button.getAttribute("data-id");
  const nome = button.getAttribute("data-nome") || "";
  const email = button.getAttribute("data-email") || "";
  const telefone = button.getAttribute("data-telefone") || "";
  const setor = button.getAttribute("data-setor") || "";
  const cargo = button.getAttribute("data-cargo") || "";

  const inputNome = document.getElementById("edit-nome");
  const inputEmail = document.getElementById("edit-email");
  const inputTelefone = document.getElementById("edit-telefone");
  const inputSetor = document.getElementById("edit-setor");
  const inputCargo = document.getElementById("edit-cargo");
  const inputSenha = document.getElementById("edit-senha");

  if (inputNome) inputNome.value = nome;
  if (inputEmail) inputEmail.value = email;
  if (inputTelefone) inputTelefone.value = telefone;
  if (inputSetor) inputSetor.value = setor;
  if (inputCargo) inputCargo.value = cargo;
  if (inputSenha) inputSenha.value = "";

  const formEditar = document.getElementById("formEditarUsuario");
  if (formEditar && IDtoEdit) {
    // endpoint do blueprint: /usuarios/editar/<id>
    formEditar.action = `/usuarios/editar/${IDtoEdit}`;
  }

  const modalEl = document.getElementById('modalEditarUsuario');
  if (!modalEl) {
    console.warn('modalEditarUsuario não encontrado');
    return;
  }

  if (window.bootstrap && bootstrap.Modal) {
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  } else {
    modalEl.classList.add('show');
    modalEl.style.display = 'block';
    modalEl.removeAttribute('aria-hidden');
  }
};

// Abrir modal de exclusão
window.abrirModalExcluir = function (id, nome, email) {
  const spanId = document.getElementById('modalUsuarioId');
  const spanNome = document.getElementById('modalUsuarioNome');
  const spanEmail = document.getElementById('modalUsuarioEmail');

  if (spanId) spanId.textContent = id;
  if (spanNome) spanNome.textContent = nome;
  if (spanEmail) spanEmail.textContent = email;

  const btn = document.getElementById('btnConfirmarExcluir');
  if (!btn) {
    console.warn('btnConfirmarExcluir não encontrado');
    return;
  }

  // Limpa listeners antigos pra não acumular
  const novoBtn = btn.cloneNode(true);
  btn.parentNode.replaceChild(novoBtn, btn);

  novoBtn.addEventListener('click', async function () {
    try {
      // Pega CSRF de qualquer form (reutiliza o de criar)
      const formData = new FormData();
      const csrfOrig = document.querySelector('#formCriarUsuario input[name="csrf_token"]');
      if (csrfOrig) {
        formData.append('csrf_token', csrfOrig.value);
      }

      // endpoint do blueprint: /usuarios/excluir/<id>
      const response = await fetch(`/usuarios/excluir/${id}`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const modalEl = document.getElementById('modalExcluirUsuario');
        const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
        modal.hide();
        window.location.reload();
      } else {
        alert('Erro ao excluir usuário!');
      }
    } catch (err) {
      console.error(err);
      alert('Erro ao excluir usuário!');
    }
  });

  const modalEl = document.getElementById('modalExcluirUsuario');
  if (!modalEl) {
    console.warn('modalExcluirUsuario não encontrado');
    return;
  }

  if (window.bootstrap && bootstrap.Modal) {
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();
  } else {
    modalEl.classList.add('show');
    modalEl.style.display = 'block';
    modalEl.removeAttribute('aria-hidden');
  }
};

// -------------------------------------------------------------------
// LÓGICA DE SUBMIT DOS FORMULÁRIOS (CRIAÇÃO E EDIÇÃO)
// -------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
  console.log('DOM carregado dentro de managUser.js');

  // BOTÕES EDITAR (sem usar onclick, só o listener)
  const botoesEditar = document.querySelectorAll('.user-page__editar-usuario-btn');
  botoesEditar.forEach(function (btn) {
    btn.addEventListener('click', function () {
      window.openEditUserModal(this);
    });
  });

  // SUBMIT CRIAR
  const formCriarUsuario = document.getElementById('formCriarUsuario');
  if (formCriarUsuario) {
    formCriarUsuario.addEventListener('submit', async function (e) {
      e.preventDefault();
      const form = e.target;
      const data = new FormData(form);

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: data
        });

        if (response.ok) {
          const modalCriarEl = document.getElementById('modalCriarUsuario');
          const modalCriar = bootstrap.Modal.getInstance(modalCriarEl) || new bootstrap.Modal(modalCriarEl);
          modalCriar.hide();

          const modalSucessoEl = document.getElementById('modalSucesso');
          const modalSucesso = new bootstrap.Modal(modalSucessoEl);
          modalSucesso.show();

          modalSucessoEl.addEventListener('hidden.bs.modal', function () {
            window.location.reload();
          }, { once: true });
        } else {
          const errorData = await response.json();
          let errorMessage = 'Erro ao criar usuário!\n';
          if (errorData.erros) {
            for (const field in errorData.erros) {
              errorMessage += `- ${field}: ${errorData.erros[field]}\n`;
            }
          }
          alert(errorMessage);
        }
      } catch (err) {
        console.error(err);
        alert('Erro ao criar usuário!');
      }
    });
  }

  // SUBMIT EDITAR
  const formEditarUsuario = document.getElementById('formEditarUsuario');
  if (formEditarUsuario) {
    formEditarUsuario.addEventListener('submit', async function (e) {
      e.preventDefault();
      const form = e.target;
      const data = new FormData(form);

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: data
        });

        if (response.ok) {
          const modalEditarEl = document.getElementById('modalEditarUsuario');
          const modalEditar = bootstrap.Modal.getInstance(modalEditarEl) || new bootstrap.Modal(modalEditarEl);
          modalEditar.hide();
          window.location.reload();
        } else {
          let msg = 'Erro ao editar usuário!';
          try {
            const json = await response.json();
            if (json.mensagem) msg = json.mensagem;
          } catch (err) {
            console.error(err);
          }
          alert(msg);
        }
      } catch (err) {
        console.error(err);
        alert('Erro ao editar usuário!');
      }
    });
  }
});
