import DefaultTheme from 'vitepress/theme';
import type {Theme} from 'vitepress';
import Baixar from './Baixar.vue';
import './estilo.css';

export default {
  extends: DefaultTheme,
  enhanceApp({app}) {
    app.component('Baixar', Baixar);
  },
} satisfies Theme;
