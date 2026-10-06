# The icons

The icons of guiqula's controls are a subset of [Tabler Icons](https://tabler.io/icons),
version 3.35.0, under the MIT licence kept in `LICENSE` next to them. Each file is
Tabler's SVG as published, saved under the name guiqula calls it by, the names
`guiqula.ui.icons.NAMES` lists; every file draws in `currentColor` alone, which
`icons.icon()` replaces by a colour of the active theme. The style is Tabler's outline
one, with one exception, `cancel`, which is the filled stop square: at 16 px the outline
square, greyed while nothing runs, reads as an empty check box, the one that the 3D switch
of the canvas bar draws. In the table a Tabler name alone is the outline style and
`filled/` names the filled one.

To fetch the whole set again, from this folder (the table below is what the loop reads):

```bash
sed -n 's/^| `\(.*\)` | `\(.*\)` | 3.35.0 |$/\1 \2/p' README.md | while read ours tabler; do
    case $tabler in */*) ;; *) tabler=outline/$tabler ;; esac
    curl -sfL -o "$ours.svg" "https://unpkg.com/@tabler/icons@3.35.0/icons/$tabler.svg"
done
```

A new icon is one more row here, its file fetched the same way, and its name in `NAMES`;
`tests/ui/test_icons.py` checks that the files, `NAMES` and this table agree, and draws
every icon in both themes.

| ours | Tabler | version |
|---|---|---|
| `new` | `file-plus` | 3.35.0 |
| `open` | `folder-open` | 3.35.0 |
| `save` | `device-floppy` | 3.35.0 |
| `undo` | `arrow-back-up` | 3.35.0 |
| `redo` | `arrow-forward-up` | 3.35.0 |
| `run` | `player-play` | 3.35.0 |
| `cancel` | `filled/player-stop` | 3.35.0 |
| `follow` | `repeat` | 3.35.0 |
| `add` | `plus` | 3.35.0 |
| `search` | `search` | 3.35.0 |
| `fit` | `maximize` | 3.35.0 |
| `pan` | `arrows-move` | 3.35.0 |
| `zoom_in` | `zoom-in` | 3.35.0 |
| `pick` | `pointer` | 3.35.0 |
| `box` | `marquee-2` | 3.35.0 |
| `lasso` | `lasso` | 3.35.0 |
| `select` | `select-all` | 3.35.0 |
| `paint` | `brush` | 3.35.0 |
| `image` | `photo-down` | 3.35.0 |
| `export` | `file-export` | 3.35.0 |
| `data` | `table-down` | 3.35.0 |
| `overlay` | `stack-2` | 3.35.0 |
| `detach` | `external-link` | 3.35.0 |
| `help` | `help` | 3.35.0 |
| `lattice` | `grid-dots` | 3.35.0 |
| `op` | `tool` | 3.35.0 |
| `term` | `sum` | 3.35.0 |
| `calculation` | `chart-dots` | 3.35.0 |
| `region` | `polygon` | 3.35.0 |
| `meanfield` | `circles-relation` | 3.35.0 |
| `python` | `brand-python` | 3.35.0 |
| `done` | `check` | 3.35.0 |
| `stale` | `rotate-clockwise` | 3.35.0 |
| `failed` | `x` | 3.35.0 |
| `locked` | `lock` | 3.35.0 |
| `log` | `logs` | 3.35.0 |
| `panels` | `layout-sidebar-right` | 3.35.0 |
| `remove` | `trash` | 3.35.0 |
| `run_stale` | `player-track-next` | 3.35.0 |
| `kspace` | `hexagon` | 3.35.0 |
| `structure` | `hexagons` | 3.35.0 |
| `theme` | `palette` | 3.35.0 |
| `3d` | `cube` | 3.35.0 |
| `show` | `eye` | 3.35.0 |
| `slider` | `adjustments-horizontal` | 3.35.0 |
| `invalid` | `alert-octagon` | 3.35.0 |
| `warning` | `alert-triangle` | 3.35.0 |
| `disabled` | `circle-off` | 3.35.0 |
| `running` | `hourglass-high` | 3.35.0 |
| `view` | `perspective` | 3.35.0 |
| `classical` | `magnet` | 3.35.0 |
| `kpath_add` | `map-pin-plus` | 3.35.0 |
| `kpath_remove` | `backspace` | 3.35.0 |
| `kpath_default` | `restore` | 3.35.0 |
| `expand` | `chevron-down` | 3.35.0 |
| `collapse` | `chevron-up` | 3.35.0 |
| `brush` | `brush` | 3.35.0 |
