/**
 * Os controles do efeito na voz, por grupo (o tom, o caráter, o ambiente e o equalizador):
 * cada um com o nome, o deslizante e o valor com a unidade. Usado pelo estúdio de voz.
 */
import React from 'react';
import {type Ajustes, comUnidade} from '../efeitos';
import type {ControleDaVoz} from '../tipos';

const GRUPOS: [ControleDaVoz['grupo'], string][] = [
  ['tom', 'Tom'], ['carater', 'Caráter'], ['ambiente', 'Ambiente'], ['equalizador', 'Equalizador'],
];

export const ControlesDaVoz: React.FC<{
  controles: ControleDaVoz[];
  ajustes: Ajustes;
  ajustar: (chave: string, valor: number) => void;
}> = ({controles, ajustes, ajustar}) => (
  <div className="grupos-da-voz">
    {GRUPOS.map(([grupo, titulo]) => (
      <fieldset key={grupo}>
        <legend>{titulo}</legend>
        {controles.filter((c) => c.grupo === grupo).map((c) => (
          <label key={c.chave} className="controle-da-voz">
            <span>{c.titulo}</span>
            <input type="range" min={c.minimo} max={c.maximo} step={1} value={ajustes[c.chave] ?? 0}
              aria-label={c.titulo} aria-valuetext={comUnidade(ajustes[c.chave] ?? 0, c)}
              onChange={(ev) => ajustar(c.chave, Number(ev.target.value))} />
            <output>{comUnidade(ajustes[c.chave] ?? 0, c)}</output>
          </label>
        ))}
      </fieldset>
    ))}
  </div>
);
