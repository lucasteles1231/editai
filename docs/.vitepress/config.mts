/**
 * O site do Editai (GitHub Pages): a documentação completa, os downloads e as versões.
 * O README é o resumo; aqui é o detalhe, e o tests/test_documentacao.py confere que os dois
 * apontam para as mesmas coisas.
 *
 * A versão mostrada é a última publicada: o workflow site.yml passa EDITAI_VERSAO.
 */
import {defineConfig} from 'vitepress';

const versao = process.env.EDITAI_VERSAO ?? '';
const repositorio = 'https://github.com/lucasteles1231/editai';

export default defineConfig({
  lang: 'pt-BR',
  title: 'Editai',
  description: 'Edita vídeos falados no estilo dos Shorts — legenda, cortes, zoom, ícones, sons e thumbnail — no seu computador.',
  base: '/editai/',
  cleanUrls: true,
  head: [
    ['link', {rel: 'icon', type: 'image/svg+xml', href: '/editai/icone.svg'}],
    ['meta', {name: 'theme-color', content: '#ffd400'}],
  ],
  themeConfig: {
    logo: '/icone.svg',
    nav: [
      {text: 'Baixar', link: '/baixar'},
      {text: 'Guia', link: '/guia/comeco-rapido', activeMatch: '/guia/'},
      {text: 'Versões', link: '/versoes'},
    ],
    sidebar: {
      '/guia/': [
        {text: 'Começar', items: [
          {text: 'Começo rápido', link: '/guia/comeco-rapido'},
          {text: 'O que ele faz', link: '/guia/o-que-ele-faz'},
          {text: 'O que cada função precisa', link: '/guia/o-que-cada-funcao-precisa'},
          {text: 'Instalação em detalhe', link: '/guia/instalacao-em-detalhe'},
        ]},
        {text: 'Usar', items: [
          {text: 'Como usar', link: '/guia/como-usar'},
          {text: 'A interface', link: '/guia/a-interface'},
          {text: 'A thumbnail', link: '/guia/a-thumbnail'},
          {text: 'A montagem em camadas', link: '/guia/a-montagem-em-camadas'},
          {text: 'Presets', link: '/guia/presets'},
          {text: 'Cartões animados', link: '/guia/cartoes-animados'},
          {text: 'A legenda em destaques', link: '/guia/a-legenda-em-destaques'},
          {text: 'O que você falou', link: '/guia/o-que-voce-falou'},
          {text: 'Voz e bipe', link: '/guia/voz-e-bipe'},
          {text: 'Efeitos na voz', link: '/guia/efeitos-na-voz'},
          {text: 'Minha voz', link: '/guia/minha-voz'},
          {text: 'Meu avatar', link: '/guia/meu-avatar'},
          {text: 'Efeitos sonoros', link: '/guia/efeitos-sonoros'},
        ]},
        {text: 'Referência', items: [
          {text: 'No terminal', link: '/guia/no-terminal'},
          {text: 'Opções de saída', link: '/guia/opcoes-de-saida'},
          {text: 'Como funciona', link: '/guia/como-funciona'},
          {text: 'Desempenho', link: '/guia/desempenho'},
          {text: 'Segurança e privacidade', link: '/guia/seguranca-e-privacidade'},
          {text: 'Dúvidas e problemas', link: '/guia/duvidas-e-problemas'},
        ]},
        {text: 'O projeto', items: [
          {text: 'Desenvolvimento', link: '/guia/desenvolvimento'},
          {text: 'Créditos e licenças', link: '/guia/creditos-e-licencas'},
          {text: 'Versões', link: '/versoes'},
        ]},
      ],
    },
    socialLinks: [{icon: 'github', link: repositorio, ariaLabel: 'O código no GitHub'}],
    search: {
      provider: 'local',
      options: {
        translations: {
          button: {buttonText: 'Buscar', buttonAriaLabel: 'Buscar na documentação'},
          modal: {
            noResultsText: 'Nada encontrado para',
            resetButtonTitle: 'Limpar a busca',
            displayDetails: 'Mostrar detalhes',
            footer: {selectText: 'abrir', navigateText: 'navegar', closeText: 'fechar'},
          },
        },
      },
    },
    outline: {level: [2, 3], label: 'Nesta página'},
    docFooter: {prev: 'Anterior', next: 'Próxima'},
    editLink: {pattern: `${repositorio}/edit/main/docs/:path`, text: 'Corrigir esta página no GitHub'},
    darkModeSwitchLabel: 'Tema',
    lightModeSwitchTitle: 'Usar o tema claro',
    darkModeSwitchTitle: 'Usar o tema escuro',
    sidebarMenuLabel: 'Menu',
    returnToTopLabel: 'Voltar ao topo',
    notFound: {
      title: 'Página não encontrada',
      quote: 'O endereço pode ter mudado de lugar na documentação.',
      linkLabel: 'Ir para o início',
      linkText: 'Voltar ao início',
    },
    footer: {
      message: `Licença MIT · <a href="${repositorio}">código no GitHub</a>` +
        (versao ? ` · versão ${versao}` : ''),
    },
  },
  vite: {
    define: {__EDITAI_VERSAO__: JSON.stringify(versao)},
    // a fonte dos títulos é a mesma do editor (editor/recursos), sem cópia aqui
    server: {fs: {allow: ['..']}},
  },
});
