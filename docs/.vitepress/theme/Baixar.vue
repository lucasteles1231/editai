<script setup lang="ts">
/**
 * O download: reconhece o sistema de quem visita e mostra primeiro o dele, com o comando de
 * uma linha (o caminho sem aviso de segurança) e o arquivo para abrir com dois cliques. Os
 * outros sistemas ficam logo abaixo. Os comandos são os mesmos de editor/versao.py
 * (tests/test_documentacao.py confere).
 */
import {computed, onMounted, ref} from 'vue';
import {withBase} from 'vitepress';

const props = defineProps<{compacto?: boolean}>();

type Id = 'mac' | 'windows' | 'linux';
type Sistema = {
  id: Id; nome: string; onde: string; comando: string;
  arquivo: string; rotulo: string; passos: string[]; atalho: string;
};

const site = 'https://lucasteles1231.github.io/editai';
const ultima = 'https://github.com/lucasteles1231/editai/releases/latest/download';
const versao = __EDITAI_VERSAO__;

const SISTEMAS: Sistema[] = [
  {
    id: 'mac', nome: 'macOS', onde: 'no Terminal (⌘ + espaço, digite "Terminal")',
    comando: `curl -LsSf ${site}/instalar.sh | sh`,
    arquivo: 'Instalar-Editai-macOS.zip', rotulo: 'Baixar o instalador para Mac (.zip)',
    passos: [
      'Abra o .zip e dê dois cliques em "Instalar Editai.command".',
      'Na primeira vez, o macOS avisa que não pode verificar quem fez o arquivo: abra Ajustes do '
        + 'Sistema → Privacidade e Segurança e clique em "Abrir Mesmo Assim". O comando acima não '
        + 'passa por esse aviso.',
    ],
    atalho: 'o Editai aparece em Aplicativos (e no Launchpad)',
  },
  {
    id: 'windows', nome: 'Windows', onde: 'no PowerShell (no menu Iniciar, digite "PowerShell")',
    comando: `powershell -ExecutionPolicy ByPass -c "irm ${site}/instalar.ps1 | iex"`,
    arquivo: 'Instalar-Editai-Windows.cmd', rotulo: 'Baixar o instalador para Windows (.cmd)',
    passos: [
      'Dê dois cliques no arquivo baixado.',
      'Se o Windows avisar que não conhece o arquivo, clique em "Mais informações" e depois em '
        + '"Executar assim mesmo".',
    ],
    atalho: 'o Editai aparece no menu Iniciar e na Área de Trabalho',
  },
  {
    id: 'linux', nome: 'Linux', onde: 'num terminal',
    comando: `curl -LsSf ${site}/instalar.sh | sh`,
    arquivo: 'instalar.sh', rotulo: 'Baixar o instalador para Linux (.sh)',
    passos: ['No terminal, na pasta do download: sh instalar.sh'],
    atalho: 'o Editai aparece no menu de aplicativos',
  },
];

const detectado = ref<Id | 'celular' | ''>('');
const copiado = ref('');

onMounted(() => {
  const nav = navigator as Navigator & {userAgentData?: {platform?: string; mobile?: boolean}};
  const texto = `${nav.userAgentData?.platform ?? ''} ${nav.platform ?? ''} ${nav.userAgent}`.toLowerCase();
  if (nav.userAgentData?.mobile || /android|iphone|ipad|ipod/.test(texto)) detectado.value = 'celular';
  else if (texto.includes('win')) detectado.value = 'windows';
  else if (texto.includes('mac')) detectado.value = 'mac';
  else if (texto.includes('linux') || texto.includes('x11')) detectado.value = 'linux';
});

const principal = computed(() => SISTEMAS.find((s) => s.id === detectado.value) ?? null);
const outros = computed(() => SISTEMAS.filter((s) => s.id !== principal.value?.id));

async function copiar(s: Sistema) {
  try {
    await navigator.clipboard.writeText(s.comando);
    copiado.value = s.id;
    setTimeout(() => (copiado.value = ''), 2000);
  } catch {
    copiado.value = '';
  }
}
</script>

<template>
  <section class="baixar" aria-label="Baixar o Editai">
    <p v-if="!versao" class="aviso-sem-versao">
      A primeira versão ainda não foi publicada. Enquanto isso, dá para instalar direto do código:
      veja a <a :href="withBase('/guia/instalacao-em-detalhe')">instalação em detalhe</a>.
    </p>
    <template v-else>
      <p class="versao">
        Versão <b>{{ versao }}</b> · <a :href="withBase('/versoes')">o que mudou</a> · grátis e de código aberto
      </p>
      <p v-if="detectado === 'celular'" class="celular">
        O Editai roda no computador: macOS, Windows ou Linux. Abra esta página nele para instalar.
      </p>

      <article v-if="principal" class="sistema principal">
        <h3 class="titulo-da-secao">Para {{ principal.nome }}</h3>
        <p>Copie e cole {{ principal.onde }}:</p>
        <div class="comando">
          <code>{{ principal.comando }}</code>
          <button type="button" class="botao-adesivo" @click="copiar(principal)">
            {{ copiado === principal.id ? 'Copiado' : 'Copiar' }}
          </button>
        </div>
        <p class="depois">Pronto: {{ principal.atalho }}. Leva uns minutos na primeira vez.</p>
        <details>
          <summary>Prefere um arquivo para abrir com dois cliques?</summary>
          <p><a class="arquivo" :href="`${ultima}/${principal.arquivo}`">{{ principal.rotulo }}</a></p>
          <ol><li v-for="p in principal.passos" :key="p">{{ p }}</li></ol>
        </details>
      </article>

      <div class="outros" :class="{todos: !principal}">
        <p v-if="principal && !props.compacto" class="titulo-outros">Outros sistemas</p>
        <article v-for="s in (props.compacto && principal ? [] : outros)" :key="s.id" class="sistema">
          <h3 class="titulo-da-secao">{{ s.nome }}</h3>
          <p>Copie e cole {{ s.onde }}:</p>
          <div class="comando">
            <code>{{ s.comando }}</code>
            <button type="button" class="botao-adesivo" @click="copiar(s)">
              {{ copiado === s.id ? 'Copiado' : 'Copiar' }}
            </button>
          </div>
          <p class="depois">Ou <a :href="`${ultima}/${s.arquivo}`">{{ s.rotulo.toLowerCase() }}</a>.</p>
        </article>
        <p v-if="props.compacto && principal" class="titulo-outros">
          Outro sistema? <a :href="withBase('/baixar')">Todos os instaladores</a>
        </p>
      </div>

      <p v-if="!props.compacto" class="somas">
        Para conferir o arquivo baixado, os hashes SHA-256 estão no
        <a :href="`${ultima}/SHA256SUMS.txt`">SHA256SUMS.txt</a> da versão.
      </p>
    </template>
  </section>
</template>

<style scoped>
/* minmax(0, 1fr): o comando comprido rola dentro da caixa, sem alargar a página */
.baixar { margin: 28px 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
.versao, .celular, .aviso-sem-versao { margin: 0; color: var(--vp-c-text-2); }
.aviso-sem-versao {
  padding: 12px 16px;
  border: 2px solid var(--vp-c-text-1);
  border-radius: 12px;
  background: var(--vp-c-tip-soft);
  color: var(--vp-c-text-1);
}
.sistema {
  min-width: 0;
  padding: 18px 20px;
  border: 2px solid var(--vp-c-divider);
  border-radius: 16px;
  background: var(--vp-c-bg-elv);
}
.sistema.principal { border: 2.5px solid var(--vp-c-text-1); box-shadow: var(--sombra); }
.sistema h3 { margin: 0 0 6px; font-size: 20px; border: 0; padding: 0; }
.sistema p { margin: 6px 0; }
.comando {
  min-width: 0;
  display: flex;
  gap: 10px;
  align-items: stretch;
  margin: 8px 0;
}
.comando code {
  flex: 1;
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  border-radius: 10px;
  background: #1a1a1a;
  color: #fffcf5;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: nowrap;
}
.comando button { padding: 0 16px; border-radius: 10px; cursor: pointer; flex: none; }
.comando button:focus-visible, .arquivo:focus-visible { outline: 3px solid var(--ciano); outline-offset: 2px; }
.depois { color: var(--vp-c-text-2); font-size: 14px; }
details { margin-top: 8px; }
summary { cursor: pointer; font-weight: 600; }
ol { margin: 8px 0 0; padding-left: 20px; color: var(--vp-c-text-2); font-size: 14px; }
.outros { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); }
.titulo-outros { grid-column: 1 / -1; margin: 6px 0 0; font-weight: 600; }
.somas { margin: 0; font-size: 13.5px; color: var(--vp-c-text-2); }
@media (max-width: 560px) {
  .comando { flex-direction: column; }
  .comando button { padding: 10px; }
}
</style>
