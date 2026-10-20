/**
 * Galeria de desenvolvimento do avatar: cada parte da biblioteca montada no manequim, com cores
 * variadas, para conferir o recorte e a vetorização de uma vez. Não vai para a página montada
 * (só o index.html entra no build).
 *
 *   npm run dev → http://localhost:5173/avatar.html
 */
import {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {type Boca, type Cores, type Escolhas, POSES, type Pose, desenharQuadro, opcoes} from './desenhar';

const BASE: Escolhas = {cabeca: 'manequim', cabelo: 'nenhum', olhos: 'ia', sobrancelhas: 'ia', nariz: 'nenhum',
  barba: 'nenhum', oculos: 'nenhum', roupa: 'nenhum', acessorio: 'nenhum', boca: 'ia', bracos: 'ia',
  cores: {pele: '#f4bf96', cabelo: '#6b4a2b', sobrancelha: '', barba: '', olho: '#4c8a52', roupa: '#3c7542',
    roupa2: '#e8e4da', oculos: '#2f2f2f', acessorio: '#2b4c7e'}};

const PELES = ['#f4bf96', '#e2a57c', '#c68642', '#8a5636', '#f7d2b6'];
const CABELOS = ['#6b4a2b', '#1f1611', '#b5562c', '#d9b26a', '#7a7a7a'];
const ROUPAS = ['#3c7542', '#c2185b', '#2b4c7e', '#f0a500', '#5b3b8a'];

function variar(i: number, e: Partial<Escolhas>, cores: Partial<Cores> = {}): Escolhas {
  return {...BASE, ...e, cores: {...BASE.cores, pele: PELES[i % 5], cabelo: CABELOS[i % 5], roupa: ROUPAS[i % 5],
    ...cores}};
}

type Item = {nome: string; e: Escolhas; pose?: Pose; boca?: Boca};

const SECOES: {titulo: string; itens: Item[]}[] = [
  {titulo: 'o manequim', itens: [{nome: 'careca', e: BASE}]},
  {titulo: 'cabelos', itens: opcoes('cabelo').map((id, i) => ({nome: id, e: variar(i, {cabelo: id})}))},
  {titulo: 'barbas', itens: opcoes('barba').map((id, i) => ({nome: id, e: variar(i, {barba: id, cabelo: 'curto'})}))},
  {titulo: 'óculos', itens: opcoes('oculos').map((id, i) => ({nome: id, e: variar(i, {oculos: id, cabelo: 'lateral'})}))},
  {titulo: 'acessórios', itens: opcoes('acessorio').map((id, i) => ({nome: id,
    e: variar(i, {acessorio: id, cabelo: id === 'brincos' ? 'raspado' : 'curto'})}))},
  {titulo: 'roupas', itens: opcoes('roupa').map((id, i) => ({nome: id, e: variar(i, {roupa: id, cabelo: 'topete'})}))},
  {titulo: 'as 12 poses (com a expressão de cada uma)', itens: POSES.map((pose, i) => ({nome: pose, pose,
    e: variar(i, {cabelo: ['topete', 'longo', 'afro', 'curto', 'lateral', 'chanel'][i % 6],
      barba: i % 3 === 0 ? 'curta' : 'nenhum', oculos: i % 4 === 1 ? 'retangulares' : 'nenhum',
      roupa: ['moletom', 'nenhum', 'jaqueta', 'camisa'][i % 4]})}))},
  {titulo: 'a fala: fechada, meia e aberta', itens: (['neutro', 'explicando'] as Pose[]).flatMap((pose, i) =>
    (['fechada', 'meia', 'aberta'] as Boca[]).map((boca) => ({nome: `${pose} · ${boca}`, pose, boca,
      e: variar(i + 2, {cabelo: i ? 'ondulado' : 'topete', barba: i ? 'nenhum' : 'cavanhaque', roupa: 'moletom'})})))},
];

const Quadro: React.FC<{item: Item}> = ({item}) => {
  const [url, setUrl] = useState('');
  useEffect(() => {
    desenharQuadro(item.e, item.pose ?? 'neutro', item.boca ?? 'fechada', 600).then((c) => setUrl(c.toDataURL()))
      .catch((x: Error) => setUrl(`erro:${x.message}`));
  }, [item]);
  return (
    <figure style={{margin: 0, textAlign: 'center', fontSize: 12}}>
      {url.startsWith('data:') ? <img src={url} width={200} height={200} alt="" style={{imageRendering: 'pixelated'}} />
        : <div style={{width: 200, height: 200}}>{url}</div>}
      <figcaption>{item.nome}</figcaption>
    </figure>
  );
};

const Galeria: React.FC = () => (
  <div style={{padding: 16, display: 'grid', gap: 14}}>
    {SECOES.map((s) => (
      <section key={s.titulo}>
        <strong>{s.titulo}</strong>
        <div style={{display: 'flex', gap: 4, flexWrap: 'wrap'}}>
          {s.itens.map((it) => <Quadro key={it.nome} item={it} />)}
        </div>
      </section>
    ))}
  </div>
);

createRoot(document.getElementById('raiz')!).render(<Galeria />);
