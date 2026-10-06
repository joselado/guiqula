---
paths:
  - "src/guiqula/ui/**"
  - "src/guiqula/remote/window.py"
  - "tests/ui/**"
  - "tools/drive.py"
  - "tools/readme_images.py"
  - "tools/make_thumbnails.py"
---

# The interface

What CLAUDE.md leaves to this file, loaded when a file of `ui/`, its tests or its tools is
read or edited: how the interface is designed and checked, the modules of `ui/` with the
widget names that the tests and the drivers read and the facts their docstrings do not
carry, and the `tools/drive.py` command that shows each feature. `tools/drive.py --help` is
the catalogue of the window's actions with their arguments and of the widget names of the
result views, the scenes, the Add menus and the start page; `--list-widgets` prints every
widget that has an `objectName`.

## Good practices

What the phase-8 plan (PLAN.md section 7) was made from, kept so that any change of `ui/`
follows it; the first five are how the interface is designed, the rest how it is built and
checked.

- Put the action where its effect appears: a "+" on the outliner section the entry will
  join, Run on the result it computes, a slider on the parameter it moves. A control a row
  or a dock away from what it acts on is what the user cannot find.
- Let the window follow the selection: the workspace, the viewport tab and the help
  follow what was selected or added, and never ask the user to find the right tab first.
- One place to choose a thing: a calculation is chosen in the outliner or by its tab, not
  in a third widget; a duplicate selector is a place to be out of sync.
- The form speaks the physics and the tooltip speaks the engine: "spinful", "superconducting
  (Nambu)", "hopping range" on the label, "add_zeeman", "requested", "sparse" in the tooltip
  and the help.
- An empty state says what to do next, in one line, where the thing will appear (the start
  page when there is no system, the plot caption when nothing was run).
- Look before designing: drive the window offscreen with `tools/drive.py` at 1200x800 (the
  small laptop) and 1600x1000, on the shipped presets, in both themes, and read the
  screenshots; let the layout settle first (ten rounds of `processEvents` and
  `QTest.qWait(100)`, as `tools/readme_images.py` does), since an unsettled grab draws
  dock tab bars twice.
- A widget's `objectName` is an API: the tests, `drive.py --widget`, the remote
  `screenshot` and `widgets` methods and the examples in this file name them. Keep a name
  when the widget moves; list every rename in the report.
- A behaviour is an action, not a click: anything the window can do is a window action in
  `WINDOW_ACTIONS` (`remote/api.py`) with an example in `tools/drive.py`'s help (tests check
  both), so that it can be driven and tested without the mouse; a new key goes in
  `ui/shortcuts.py` and the tooltip names it through `shortcuts.text`.
- The Add menus, the start page's lattices, the forms, the tooltips and the help are
  generated from the registry declarations: a control that lists physics entries reads
  `registry.entries(family)`, never a hand-written list, so a plugin's entries appear in it
  too.
- The UI process stays light: pictures are PNG files made by a tool script and shipped,
  never computed in the window; `tests/ui/test_startup.py` keeps the startup budget and
  the module set (no pyqula, jax or numba).
- Replace a look, keep the instance: the matplotlib toolbar stays, hidden, behind guiqula's
  own buttons, since `CanvasNavigation` and the tests read its mode; the Inkscape and
  Blender controls of the drawings are not touched by a change of bars.
- Nothing floats: a detached thing is a plain window, since a floating dock cannot be moved
  on Wayland (decision 88).
- Layout is tested, not eyeballed: a test checks that no toolbar shows its extension
  chevron at 1200 px and no outliner status is elided at the default width, on every
  preset; every control has a tooltip (`test_every_toolbar_control_and_palette_entry_has_a_tooltip`).
- Acceptance is a named screenshot: each change states the `drive.py` command, the preset,
  the size and the theme that show it, so the maintainer can reproduce it and the next
  agent can check it.
- Work is cut by file ownership: `ui/mainwindow.py` is the shared file, so the packages
  that rewrite parts of it go one after another and the file owners (`forms.py`,
  `structure.py`, `outliner.py`, a new module) go in parallel in worktrees, merged in a
  fixed order with the suite run after each merge.
- Decisions go in PLAN.md, numbered, the recommended option first (CLAUDE.md, What this
  is); the documentation (`src/guiqula/docs/user_guide.md`, the README, CLAUDE.md's code
  map and this file) is the last package of any change, in the voice of `~/.claude/CLAUDE.md`.

## The modules of `ui/`

The window as PLAN.md section 4 draws it since phase 8. Each module's docstring says what
it is and what it builds; what follows is the widget names and the behaviour that the
tests, `drive.py --widget` and the remote `widgets` and `screenshot` methods rely on.

- `mainwindow.py`: the first toolbar row of the workspace tabs, which follow the selection
  (`workspace_of`), New system and Add (`PaletteMenu`s, which the outliner's "+" open too,
  `open_add_menu`) and the run controls (`runButton` names `selected_calculation()`: the
  outliner's calculation, else the tab's, else the first; its `runMenu`, `cancelButton`,
  Follow); `centralStack`, the start page in the viewport's place while the document has no
  system (`show_start`); the panels, `Dock`s without a float button, Properties over Help,
  Sliders and Jobs, the Log and the Console hidden behind the status bar's `logToggle`;
  View > Panels, Reset layout and Interface text, the arrangement kept in the settings
  (`layout`, `LAYOUT_VERSION`); one result view per calculation, whose tab, status row and
  outliner row read one state (`_result_state`, `marks.calculation_state`); the cost guard
  and auto re-run; the window's own dispatcher actions, which `WINDOW_ACTIONS` lists (a new
  one joins that list and `tools/drive.py`'s help; tests check both); File > Allow remote
  control starts the server, polled from the window's timer; a pick emits ordinary
  commands, and the pick menu is built by `pick_menu` and shown with `popup()`, never
  `exec()`; `pick` and `pick_to` take a calculation and a point, or `system` and `values`
  (the k-space tab's click, Calculate on selection); the viewport's tab bar is a
  `ResultTabBar` (`ui/grid.py`), the New grid button `newGridButton` its corner widget and
  View > New grid of results `newGridAction`; a result view is in one place at a time, its
  tab, its `ResultWindow` or a cell of a grid (`grids`), moved by `place_result` (the
  `grid_place` action), `_unplace` and `_to_tab`, and `current_tab()` reads `grid:<id>`
  while a grid is shown.
- `start.py`: the start page, `startPage`: the lattices, the examples and the recent files
  as cards with the pictures of `resources/thumbnails/`, a filter (where Ctrl+F puts the
  focus while the page shows, `focus_search` returning "start"), Show all with its chevron
  (`Band.set_more_icon`), the footer `startFooter` under the scroll area rather than in
  it, so in sight at large text on 1200x800; a card is made,
  and its picture read, when it comes into sight, one row of each band at start, so a
  folded card is no widget for `findChild`, `drive.py --widget` or the remote methods
  until Show all, the `start` action's filter or `StartPage.card()` makes it, and
  `Band._chain` puts a card made later in its band's Tab order; `preset_card` makes the
  gallery's cards too. `tests/ui/test_start.py` fails for a lattice, a classical system or
  a preset without a picture in `resources/thumbnails/`.
- `palette.py`: `PaletteMenu`, the Add menu of one family: a search line, the entries by
  group, `search_entries`, Enter adding the best match; `MenuButton`, which opens its menu
  with `popup()`.
- `canvasbar.py`: `CanvasBar`, the bar of a drawing: Fit, Pan, Zoom, the drawing's tools
  and Save image, in groups that wrap onto further lines, over a hidden
  `NavigationToolbar2QT` kept as `canvas.toolbar` (`HiddenToolbar`), whose mode
  `CanvasNavigation` and the tests read.
- `marks.py`: the marks of a state, one set for the outliner, the result tabs and the
  status row (`mark`, `calculation_state`); no Qt.
- `icons.py`: `icon(name, color="TEXT")`, an SVG of `resources/icons/` drawn in a colour of
  the active theme, grey when disabled, cached per theme and emptied by `theme.apply`;
  `follow(widget, method)` sets a widget's icons at its first show and again after every
  change of theme (`on_theme_change`), which is how a control gets its icon, so nothing out
  of sight costs the start, and again after a change of View > Interface text
  (`text_changed`), `size()` being 16 px or 20 px at large text; pixmaps at 16 and 24 px
  (and 20 px while the text is large), since a Python `QIconEngine` subclass
  crashes PySide6 6.11; a checkable menu entry gets no icon, which would hide its check
  box. `resources/icons/` holds the 59 Tabler Icons of the controls (SVG files drawn in
  `currentColor`, outline but the filled `cancel`, their MIT licence) and a README whose
  table of our names, Tabler's names and styles is what its fetch loop and
  `tests/ui/test_icons.py` read; a new icon is a row there, its file and its name in
  `icons.NAMES`.
- `help.py`: the Help panel, below Properties: F1, a form's ?, the guides, the search line
  `helpSearch` (Shift+F1, decision 159), whose results page links entries
  (`help:entry/<family>:<kind>`, `show_entry`) and sections; a page is a tuple
  (`page`) that `show_page` shows again for Back and a redraw; Markdown in a
  QTextBrowser, whose `loadResource` serves the equations; the lines of a code block wrap
  at the panel's width (`_wrap_code`) and an equation wider than the panel is scaled down
  to it (`_fit_equations`), so no page scrolls sideways; the section's name wraps, since a
  label one line long sets the column's minimum width (as the Jobs panel's workers line did).
- `shortcuts.py`: the one table of keyboard shortcuts (menus, the canvas and outliner keys,
  the dialog); a test refuses ambiguous keys, and the shortcut table of
  `src/guiqula/docs/user_guide.md` is checked against it.
- `outliner.py`: the tree: a "+" on each section row (`outlinerAdd_<system>_<section>`,
  `outlinerAdd_calculations`, `add_requested`); a label that says what the row is, after
  the icon of its kind (`KIND_ROLE`, `structure` or `classical` for a system), wrapped at
  its spaces onto further lines (a Unicode line separator, `LINE`, since Qt drops a
  newline of an item's text) when wider than its room (`EntryDelegate.label_room`), and
  elided only when a word is wider than that (`wraps`); a Status column that holds the
  state only and is as wide as its longest text (`status_width`), its marks drawn as icons
  at paint time (`status_parts`, `draw_parts`, `MARK_ROLE`), a warning the triangle and an
  invalid entry the octagon, while its text keeps `marks.py`'s Unicode, which the
  tooltips and the tests read; the system and the mean field as detail rows across both
  columns, their marks icons too (`leading_marks` when the status reads under the label);
  a section row's "+" as high as its first line (`first_line`), so a wrapped label does not
  widen the Status column. `tests/ui/test_outliner.py`'s `cut` checks the labels as well as
  the statuses on every preset.
- `gallery.py` (the presets, the start page's cards and `Title` headings, deleted when
  closed), `sliders.py` (the Sliders panel;
  `range_from`, the range a label's menu gives a slider or a sweep), `kspace.py` (the
  Brillouin-zone canvas, its tab hidden for a system without a periodic direction, its
  path tools `kpathAdd`, `kpathRemoveLast` and `kpathDefault` icons alone in its bar),
  `jobpanel.py`, `console.py` (the console panel), `bars.py` (recovery, error, cost and
  trust bars; `StatusMessage`, the last message in the status bar), `errors.py` (the
  exception hook), `formulas.py` (mathtext images; the rich tooltips of the Add menus).
- `properties.py` and `forms.py`: forms from the parameter declarations, in the words of
  the physics: the label's menu `paramMenu_<p>` (Lock, Attach a slider, Sweep this
  parameter, Preview on the canvas), the region link, a calculation's estimate and
  `formRun` in the footer of the panel (`propertiesFooter`) under the scrolled form
  (`propertiesScroll`; the panel `properties` is a QWidget since P8, and its
  `verticalScrollBar()` is the form's); the system form's spin, Nambu, hopping range and
  sparse; the Field editor, whose button shows the kind and opens the kind menu
  `fieldKindMenu_<p>`, every kind button of a form as wide as the widest (`line_up`).
- `structure.py`: the canvas (`structureView`), its three views (structure, Hamiltonian,
  field), its bar `structureBar` with the selection tools, and the mplot3d drawing of
  geometries that are not flat.
- `pyvista_view.py`: the 3D drawing with pyvista (View > 3D drawing, the `renderer_3d`
  action and setting; pyvista unless matplotlib was chosen or pyvista is missing): rendered
  off-screen and painted as an image, since a `QVTKRenderWindowInteractor` embedded in Qt
  segfaults on the offscreen platform; moved as Blender's viewport is, the widget applying
  the mouse and the numpad to a `navigation.Turntable` and setting the camera
  (`SceneCanvas.send`/`drag` without a mouse, `SceneView.set_view` and the `view_3d`
  action); pyvista imported at the first drawing, never at startup; the canvas
  (`structureScene`) and each `PlotView` (`plotScene_<id>`) swap their matplotlib canvas for
  its `SceneView`, whose Reset view, View and Save image go into the drawing's bar, and a
  result on the atoms follows the canvas's projection. pyvista renders off-screen through
  XWayland here and falls back to EGL by itself without a display.
- `navigation.py` (the arithmetic of moving, without Qt, VTK or matplotlib: `Turntable`,
  the limits of a flat view, `ZoomHistory`), `canvas_navigation.py` (Inkscape's controls on
  a matplotlib canvas, `CanvasNavigation`, on the structure canvas and the results drawn
  flat on the atoms; `bind_keys` makes the QShortcuts of the table's "2D canvas" context;
  the "3D canvas" keys are the scene's own `keyPressEvent`).
- `plots.py`: `PlotView` per calculation (`plot_<id>`, its bar `plotBar_<id>`, its status
  row `plotStatus_<id>` with the state's icon `plotStatusMark_<id>`: stale with Run again,
  queued or running with the progress and Cancel, failed; `ROW_STATES`), and
  `ResultWindow`, the plain window of a detached one, never a floating dock, which Wayland
  cannot move; the plot kinds lines, colored_scatter, heatmap, structure_scalar,
  structure_vector, scalar; the right click, the Pick, Box and Lasso toggles
  (`pick_requested`); the markers, sliders with `on` drawn by `set_markers` and dragged
  through `marker_moved`; the Style button `style_<id>` (the brush, beside Overlay),
  whose popup `stylePopup_<id>` holds one control per option of the kind,
  `style_<option>_<id>`, and `styleReset_<id>`; a change is reported (`style_changed`) and
  the window dispatches `plot_style`, which calls `restyle`, the same result drawn again
  with its limits kept. `draw(..., style=)` takes the style, so the export does too.
- `grid.py`: the grids of result views (decisions 170 to 180): `GridView` (`grid_<id>`, its
  bar `gridBar_<id>` with `gridRows_<id>`, `gridCols_<id>` and `gridSave_<id>`), its cells
  `gridCell_<id>_<row>_<col>` with the title `gridCellTitle_<id>_<row>_<col>`, the ×
  `gridRelease_<id>_<row>_<col>` and the empty state `gridEmpty_<id>_<row>_<col>`, each cell
  an equal share of the grid (an `Ignored` size policy); `ResultTabBar`, the viewport's tab
  bar, from which a result's tab is dragged and onto which a title is dropped. A drag
  carries the calculation id as `MIME`; a drop only asks the window, which places the view
  through the `grid_place` action after the drag has returned (a `QTimer.singleShot`, since
  the drop may take a tab from the very bar dragging it). A test sends a `QDragEnterEvent`
  before the `QDropEvent`: Qt delivers no drop to a widget a drag did not enter, and a real
  `QDrag` does not run offscreen.
- `plotstyle.py`: the catalogue of the cosmetics per plot kind (`OPTIONS`, decisions 164
  to 169: name, label, type, default, range or choices, tip), `clean` (what differs from
  the defaults, strict or not), `resolve` (every option with its value), and `StylePopup`;
  a default of None is decided when drawing (the spec's colour map, the theme's colour).
  The structure drawings take the style as keywords (`atom_size`, `bonds`, the `cmap` of
  `site_values`, the `length`, `width`, `color` and `cmap` of `arrows`), `on_atoms(result,
  style)` making them, and so does pyvista's `draw_scene`.
- `theme.py`: light and dark (the colour names are the active theme's, rebound by `apply`);
  every figure is drawn inside `theme.drawing(figure)`, whose rc carries the plot text size
  (`text_size`, View > Plot text); the interface text (`UI_POINTS`, `set_ui_text`, View >
  Interface text); `CheckStyle`, the proxy style drawing the check boxes; `centre` and
  `Centring`, the axes box kept in the middle of its figure after every draw.
- The window saves its view state as the Document's `ui` block (not a Command, not an
  unsaved change) and restores it on open and recovery. It polls the session from a
  `QTimer` and starts the workers after it is shown; a form or tree rebuilt from inside one
  of its own signals must be deleted later (PLAN.md phase 2 facts). `tests/ui/test_icons.py`
  draws every icon in both themes and checks the controls that carry one;
  `tests/ui/test_look.py` checks the look of phase 8 (Run in sight under a long form, the
  fonts and formulas at large text, the scene's bar on two lines, an empty result view in
  the theme); `tests/ui/test_pyvista_view.py` skips without pyvista.

## Looking at a change

Each change states the `drive.py` command, the preset, the size and the theme that show
it. The commands below show one feature each (`--do` runs before `--run`, `--python`
after; the JSON report comes last; `--size WxH` sets the window):

```bash
python tools/drive.py --no-session --widget startPage --shot start.png   # the start page
python tools/drive.py --no-warm --do '{"do": "start", "search": "kagome"}' --shot kagome.png
                                                   # its filter, on an empty document
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "add_menu", "section": "s1/hamiltonian",
    "search": "spin"}' --widget paletteMenu_term --shot terms.png   # the "+" of a section
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select", "entry": "c2"}' \
    --widget runButton --shot run.png              # Run names what it runs ("Run c2 · dos")
python tools/drive.py honeycomb_zeeman_rashba --run c1 --python "session.do('set_param', \
    entry='t1', name='m', value=[0, 0, 0.3])" --widget plotStatus_c1 --shot stale.png
                                                   # the status row of a stale result
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "log"}' --do '{"do": "ui_text",
    "name": "large"}' --shot large_text.png        # the Log toggle, the interface text
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select_sites", "box": [0.9, -2, 2.1, 2]}' \
    --do '{"do": "remove_selected"}' --widget structureView --shot sculpted.png
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "canvas_view", "name": "hamiltonian"}' \
    --widget structureView --shot hview.png        # the Hamiltonian view (13.8)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "preview", "entry": "t1", "param": "m"}' \
    --widget structureView --shot field.png        # a Field on the structure
python tools/drive.py honeycomb_hubbard --run c1 --widget plot_c1 --shot hubbard.png   # mean field
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "console", "code": "h.get_gap()"}'
                                                   # the console; its output is in the report
python tools/drive.py project.guiqula --trust ...   # run the Python nodes of a file (13.7)
python tools/drive.py --recover --shot recovered.png   # unsaved work of a killed session
                                                   # (--hold SECONDS keeps the window running)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "theme", "name": "dark"}' --shot dark.png
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "plot_text", "name": "large"}' \
    --run c1 --widget plot_c1 --shot large.png     # the plot text size (small, normal, large)
python tools/drive.py honeycomb_hubbard --do '{"do": "renderer_3d", "name": "pyvista"}' \
    --do '{"do": "projection", "name": "3d"}' --do '{"do": "add_calculation", "system": "s1",
    "kind": "magnetization", "params": {"nk": 4}}' --run c3 --widget plot_c3 --shot m.png
                                                   # the 3D drawing with pyvista
python tools/drive.py honeycomb_hubbard --do '{"do": "renderer_3d", "name": "pyvista"}' \
    --do '{"do": "projection", "name": "3d"}' --do '{"do": "view_3d", "name": "top"}' \
    --widget structureScene --shot top.png             # Blender's views: front, right, top, ...
python tools/drive.py preset --do '{"do": "set_param", ...}' --do '{"do": "undo"}'
                                                   # undo, redo (steps), history
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "select", "entry": "t1"}' \
    --do '{"do": "help"}' --widget helpDock --shot help.png   # an entry's help (13.13)
python tools/drive.py honeycomb_zeeman_rashba --do '{"do": "help", "search": "rashba spin orbit"}' \
    --widget helpDock --shot search.png            # the search of the help (decision 159)
python tools/drive.py honeycomb_zeeman_rashba --run c1 \
    --python "session.act('export_bundle', calculation='c1', path='out/c1_bands')"
                                                   # figure, data, script in one folder
python tools/drive.py honeycomb_zeeman_rashba --run c2 --python "session.act('plot_style', \
    calculation='c2', linewidth=3, color='#d62728', fill=True); \
    window.plots['c2'].open_style()" --widget stylePopup_c2 --shot style.png
                                                   # the style of a plot (decisions 164 to 169)
python tools/drive.py honeycomb_zeeman_rashba --size 1600x1000 --run c1 --run c2 \
    --do '{"do": "grid"}' --python "session.act('grid_place', calculation='c1', grid='g1', \
    row=0, col=1); session.act('grid_place', calculation='c2', grid='g1', row=1, col=1)
from PySide6.QtTest import QTest
for _ in range(10): QTest.qWait(100)" --widget viewport --shot grid.png
                                                   # a grid of results (decisions 170 to 180)
python tools/drive.py honeycomb_zeeman_rashba --run c1 --python "session.act('run_at_once'); \
    p = session.act('pick', calculation='c1', x=20, y=0.5); print(p['label'], \
    [t['label'] for t in p['targets']]); session.act('pick_to', calculation='c1', x=20, \
    y=0.5, target=0)"                              # a pick on the bands (phase 7)
PYTHONPATH=src python -m guiqula --remote preset      # the window, remote control on (3.7)
```
