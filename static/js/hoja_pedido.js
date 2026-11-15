/* Hoja de pedido: componentes compartidos por el escáner (local) y la pantalla Despacho.
 *
 * Dibuja los tiempos del menú con sus botones grandes (plato y, si corresponde, su
 * acompañamiento), el estado de cada opción (quedan N, pocas, agotado) y valida que la
 * selección esté completa. No reserva ni registra nada: eso lo decide cada pantalla.
 *
 * menu:      { tiempos: [{ id, nombre, obligatorio, platos: [{ id, nombre, quedan, estado, acompanamientos: [...] }] }] }
 * seleccion: { <tiempoId>: { plato: id, acompanamiento: id | null } }
 */
(function () {
    const ESTADO_TEXTO = { agotado: "Agotado", reservada_por_otro: "Agotado (reservada por otro garzón)" };

    function elemento(tag, clase, texto) {
        const nodo = document.createElement(tag);
        if (clase) nodo.className = clase;
        if (texto !== undefined) nodo.textContent = texto;
        return nodo;
    }

    const libre = (item) => Boolean(item) && !["agotado", "reservada_por_otro"].includes(item.estado);
    const buscarPlato = (tiempo, id) => tiempo.platos.find((p) => p.id === id);

    function textoQuedan(item) {
        if (!libre(item)) return ESTADO_TEXTO[item.estado] || "Agotado";
        return item.quedan === null ? "" : `quedan ${item.quedan}`;
    }

    function botonOpcion(item, seleccionado, alTocar) {
        const boton = elemento("button", "cq-opcion");
        boton.type = "button";
        if (seleccionado) boton.classList.add("is-selected");
        if (!libre(item) && !seleccionado) { boton.classList.add("is-off"); boton.disabled = true; }
        else if (item.estado === "bajo") boton.classList.add("is-low");
        boton.append(elemento("strong", "", item.nombre));
        const quedan = textoQuedan(item);
        if (quedan) boton.append(elemento("span", "", quedan));
        boton.addEventListener("click", alTocar);
        return boton;
    }

    function tiempoCompleto(tiempo, seleccion) {
        const elegido = seleccion[tiempo.id];
        if (!elegido) return false;
        const plato = buscarPlato(tiempo, elegido.plato);
        return Boolean(plato) && (!plato.acompanamientos.length || Boolean(elegido.acompanamiento));
    }

    /** Todos los obligatorios completos, algo elegido y nada a medias (plato sin acompañamiento). */
    function seleccionLista(menu, seleccion) {
        return menu.tiempos.every((t) => !t.obligatorio || tiempoCompleto(t, seleccion))
            && Object.keys(seleccion).length > 0
            && menu.tiempos.every((t) => !seleccion[t.id] || tiempoCompleto(t, seleccion));
    }

    /** Dibuja la hoja en `contenedor`. `alTocarPlato(tiempo, plato)` y `alTocarAcomp(tiempo, plato, acomp)`. */
    function pintar(contenedor, menu, seleccion, { alTocarPlato, alTocarAcomp }) {
        contenedor.replaceChildren();
        menu.tiempos.forEach((tiempo) => {
            const fila = elemento("section", "cq-pedido-tiempo");
            fila.append(elemento("h3", "", tiempo.obligatorio ? tiempo.nombre : `${tiempo.nombre} (opcional)`));
            const opciones = elemento("div", "cq-opciones");
            const elegido = seleccion[tiempo.id];
            tiempo.platos.forEach((plato) => {
                opciones.append(botonOpcion(plato, Boolean(elegido) && elegido.plato === plato.id, () => alTocarPlato(tiempo, plato)));
            });
            fila.append(opciones);
            const platoElegido = elegido && buscarPlato(tiempo, elegido.plato);
            if (platoElegido && platoElegido.acompanamientos.length) {
                const acomps = elemento("div", "cq-opciones cq-opciones-sub");
                platoElegido.acompanamientos.forEach((acomp) => {
                    acomps.append(botonOpcion(acomp, elegido.acompanamiento === acomp.id, () => alTocarAcomp(tiempo, platoElegido, acomp)));
                });
                fila.append(acomps);
            }
            contenedor.append(fila);
        });
    }

    /** Texto corto de la selección: «Pollo asado · Chuleta + Arroz». */
    function resumen(menu, seleccion) {
        const partes = [];
        menu.tiempos.forEach((tiempo) => {
            const elegido = seleccion[tiempo.id];
            const plato = elegido && buscarPlato(tiempo, elegido.plato);
            if (!plato) return;
            const acomp = elegido.acompanamiento && plato.acompanamientos.find((a) => a.id === elegido.acompanamiento);
            partes.push(acomp ? `${plato.nombre} + ${acomp.nombre}` : plato.nombre);
        });
        return partes.join(" · ");
    }

    window.HojaPedido = { pintar, seleccionLista, tiempoCompleto, libre, buscarPlato, textoQuedan, resumen };
})();
