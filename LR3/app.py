import math
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


EXAMPLE = """G+(1) = {2}
G+(2) = {3, 4}
G+(3) = {1}
G+(4) = {5}
G+(5) = {4, 6}
G+(6) = {}
G+(7) = {6}"""

COLORS = ["#2563eb", "#dc2626", "#059669", "#9333ea",
          "#ea580c", "#0891b2", "#4f46e5", "#be123c"]


def read_graph(text):
    """Чтение множества правых инциденций G+ из текста."""
    graph = {}
    pattern = re.compile(
        r"^\s*(?:G\s*\+?\s*\(\s*)?(\d+)(?:\s*\))?\s*(?:=|:|->|→)\s*(.*?)\s*$",
        re.I,
    )

    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        found = pattern.match(line)
        if not found:
            raise ValueError(
                f"Строка {line_number}: используйте формат G+(1) = {{2, 3}}"
            )

        vertex = int(found.group(1))
        if vertex < 1:
            raise ValueError(f"Строка {line_number}: номер должен быть положительным")
        if vertex in graph:
            raise ValueError(f"Строка {line_number}: вершина {vertex} указана дважды")

        value = found.group(2).strip().strip("{}[]() ")
        if value.lower() in ("", "ø", "∅", "-", "нет", "0"):
            graph[vertex] = []
            continue

        targets = []
        for word in re.split(r"[\s,;]+", value):
            if not word.isdigit() or int(word) < 1:
                raise ValueError(
                    f"Строка {line_number}: «{word}» не является номером вершины"
                )
            number = int(word)
            if number not in targets:
                targets.append(number)
        graph[vertex] = sorted(targets)

    if not graph:
        raise ValueError("Введите хотя бы одну вершину")

    # Вершины, встречающиеся только справа, тоже принадлежат графу.
    all_vertices = set(graph)
    for targets in graph.values():
        all_vertices.update(targets)
    for vertex in all_vertices:
        graph.setdefault(vertex, [])
    return dict(sorted(graph.items()))


def closure(start, graph):
    """Множество вершин, достижимых из start (включая start)."""
    found = {start}
    stack = [start]
    while stack:
        vertex = stack.pop()
        for neighbour in graph[vertex]:
            if neighbour not in found:
                found.add(neighbour)
                stack.append(neighbour)
    return sorted(found)


def incidence(vertices, arcs):
    """Матрица B: +1 — начало, -1 — конец, 2 — петля."""
    matrix = []
    for vertex in vertices:
        row = []
        for arc in arcs:
            start, end = arc[1], arc[2]
            if start == vertex and end == vertex:
                row.append(2)
            elif start == vertex:
                row.append(1)
            elif end == vertex:
                row.append(-1)
            else:
                row.append(0)
        matrix.append(row)
    return matrix


def analyze(text):
    graph = read_graph(text)
    vertices = list(graph)

    # Дуги: (номер, начало, конец).
    arcs = []
    for start in vertices:
        for end in graph[start]:
            arcs.append((len(arcs) + 1, start, end))

    left = {vertex: [] for vertex in vertices}
    for _, start, end in arcs:
        left[end].append(start)

    reachable = {v: closure(v, graph) for v in vertices}  # R(v)
    counter = {v: closure(v, left) for v in vertices}     # Q(v)

    # Подсистема S(v) = R(v) ∩ Q(v).
    remaining = set(vertices)
    subsystems = []
    while remaining:
        v = min(remaining)
        subsystem = sorted(set(reachable[v]) & set(counter[v]))
        subsystems.append(subsystem)
        remaining.difference_update(subsystem)

    subsystem_of = {}
    for number, members in enumerate(subsystems, 1):
        for vertex in members:
            subsystem_of[vertex] = number

    internal = [[] for _ in subsystems]
    incoming = [[] for _ in subsystems]
    outgoing = [[] for _ in subsystems]
    connections = {}

    for number, start, end in arcs:
        s1, s2 = subsystem_of[start], subsystem_of[end]
        if s1 == s2:
            internal[s1 - 1].append(number)
        else:
            outgoing[s1 - 1].append(number)
            incoming[s2 - 1].append(number)
            connections.setdefault((s1, s2), []).append(number)

    # Дуги нового графа: (номер, начало, конец, исходные дуги).
    new_arcs = []
    for number, ((start, end), old_arcs) in enumerate(
        sorted(connections.items()), 1
    ):
        new_arcs.append((number, start, end, old_arcs))

    return {
        "graph": graph, "vertices": vertices, "arcs": arcs, "left": left,
        "reachable": reachable, "counter": counter, "subsystems": subsystems,
        "internal": internal, "incoming": incoming, "outgoing": outgoing,
        "new_arcs": new_arcs, "matrix": incidence(vertices, arcs),
        "new_matrix": incidence(list(range(1, len(subsystems) + 1)), new_arcs),
    }


def show_set(values, prefix=""):
    if not values:
        return "∅"
    return "{" + ", ".join(prefix + str(value) for value in values) + "}"


def matrix_text(vertices, arcs, matrix, row_prefix, column_prefix):
    if not arcs:
        return ["  Нет столбцов: в графе нет дуг."]
    result = [" " * 7 + "".join(f"{column_prefix + str(a[0]):>5}" for a in arcs)]
    for vertex, row in zip(vertices, matrix):
        result.append(
            f"  {row_prefix}{vertex:<4}" + "".join(f"{value:>5}" for value in row)
        )
    return result


def make_report(data):
    lines = [
        "ТОПОЛОГИЧЕСКАЯ ДЕКОМПОЗИЦИЯ ГРАФА", "",
        f"Вершин: {len(data['vertices'])}", f"Дуг: {len(data['arcs'])}",
        f"Подсистем: {len(data['subsystems'])}", "", "Дуги исходного графа:",
    ]
    if data["arcs"]:
        for number, start, end in data["arcs"]:
            lines.append(f"  e{number}: {start} → {end}")
    else:
        lines.append("  Дуг нет")

    lines += ["", "Множества достижимости:"]
    for v in data["vertices"]:
        lines.append(
            f"  i={v}: R={show_set(data['reachable'][v])}; "
            f"Q={show_set(data['counter'][v])}"
        )

    lines += ["", "Выделенные подсистемы:"]
    for i, members in enumerate(data["subsystems"], 1):
        lines.append(f"  S{i}: вершины {show_set(members)}")
        lines.append(f"      внутренние дуги: {show_set(data['internal'][i-1], 'e')}")
        lines.append(f"      входящие дуги: {show_set(data['incoming'][i-1], 'e')}")
        lines.append(f"      исходящие дуги: {show_set(data['outgoing'][i-1], 'e')}")

    lines += ["", "Дуги графа подсистем:"]
    if data["new_arcs"]:
        for number, start, end, old in data["new_arcs"]:
            lines.append(
                f"  E{number}: S{start} → S{end}; исходные дуги {show_set(old, 'e')}"
            )
    else:
        lines.append("  Между подсистемами дуг нет")

    lines += ["", "Матрица B исходного графа:"]
    lines += matrix_text(data["vertices"], data["arcs"], data["matrix"], "v", "e")
    lines += ["", "Матрица B графа подсистем:"]
    subsystem_numbers = list(range(1, len(data["subsystems"]) + 1))
    lines += matrix_text(
        subsystem_numbers, data["new_arcs"], data["new_matrix"], "S", "E"
    )
    lines += ["", "+1 — начало дуги; -1 — конец дуги; 2 — петля."]
    return "\n".join(lines)


class GraphApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Топологическая декомпозиция графа")
        self.geometry("1200x760")
        self.minsize(900, 600)
        self.data = None
        self.create_widgets()
        self.input.insert("1.0", EXAMPLE)
        self.after(100, self.calculate)

    def create_widgets(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        ttk.Label(self, text="Выделение подсистем в структурной модели",
                  font=("Arial", 16, "bold"), padding=12).pack(fill="x")

        panels = ttk.Panedwindow(self, orient="horizontal")
        panels.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        left = ttk.Frame(panels, padding=10)
        right = ttk.Frame(panels)
        panels.add(left, weight=1)
        panels.add(right, weight=3)

        ttk.Label(left, text="Множество правых инциденций G⁺",
                  font=("Arial", 11, "bold")).pack(anchor="w")
        ttk.Label(left, text="Пример: G+(1) = {2, 3}\nили: 1: 2 3").pack(
            anchor="w", pady=(3, 7)
        )
        self.input = tk.Text(left, width=31, font=("Courier", 11), undo=True)
        self.input.pack(fill="both", expand=True)
        ttk.Button(left, text="Выполнить анализ", command=self.calculate).pack(
            fill="x", pady=(8, 4)
        )
        buttons = ttk.Frame(left)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Пример", command=self.load_example).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(buttons, text="Очистить", command=self.clear).pack(
            side="left", fill="x", expand=True, padx=4
        )
        self.save_button = ttk.Button(
            buttons, text="Сохранить", command=self.save, state="disabled"
        )
        self.save_button.pack(side="left", fill="x", expand=True)
        ttk.Button(left, text="Справка", command=self.help).pack(fill="x", pady=(4, 0))

        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        result_tab = ttk.Frame(self.tabs)
        matrix_tab = ttk.Frame(self.tabs)
        new_matrix_tab = ttk.Frame(self.tabs)
        graph_tab = ttk.Frame(self.tabs)
        self.tabs.add(result_tab, text="Результат")
        self.tabs.add(matrix_tab, text="B исходного графа")
        self.tabs.add(new_matrix_tab, text="B графа подсистем")
        self.tabs.add(graph_tab, text="Графы")

        self.result_text = tk.Text(result_tab, font=("Courier", 10), wrap="word")
        result_scroll = ttk.Scrollbar(result_tab, command=self.result_text.yview)
        self.result_text.config(yscrollcommand=result_scroll.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        result_scroll.pack(side="right", fill="y")

        self.matrix_frame = ttk.Frame(matrix_tab, padding=8)
        self.matrix_frame.pack(fill="both", expand=True)
        self.new_matrix_frame = ttk.Frame(new_matrix_tab, padding=8)
        self.new_matrix_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(graph_tab, bg="#f8fafc", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.draw_graphs())

        self.status = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w",
                  padding=4).pack(fill="x")
        self.bind("<Control-Return>", lambda event: self.calculate())

    def calculate(self):
        try:
            self.data = analyze(self.input.get("1.0", "end"))
        except ValueError as error:
            self.status.set("Ошибка ввода")
            messagebox.showerror("Ошибка", str(error), parent=self)
            return

        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", make_report(self.data))
        self.result_text.config(state="disabled")
        self.show_matrix(self.matrix_frame, self.data["vertices"], self.data["arcs"],
                         self.data["matrix"], "v", "e")
        subsystem_numbers = list(range(1, len(self.data["subsystems"]) + 1))
        self.show_matrix(self.new_matrix_frame, subsystem_numbers,
                         self.data["new_arcs"], self.data["new_matrix"], "S", "E")
        self.draw_graphs()
        self.save_button.config(state="normal")
        self.status.set(
            f"Вершин: {len(self.data['vertices'])}; дуг: {len(self.data['arcs'])}; "
            f"подсистем: {len(self.data['subsystems'])}"
        )

    def show_matrix(self, frame, vertices, arcs, matrix, row_prefix, column_prefix):
        for widget in frame.winfo_children():
            widget.destroy()
        if not arcs:
            ttk.Label(frame, text="В графе нет дуг.", padding=20).pack(anchor="nw")
            return

        columns = ["vertex"] + [f"arc{a[0]}" for a in arcs]
        table = ttk.Treeview(frame, columns=columns, show="headings")
        table.heading("vertex", text="Вершина")
        table.column("vertex", width=80, anchor="center", stretch=False)
        for arc in arcs:
            name = f"arc{arc[0]}"
            table.heading(name, text=f"{column_prefix}{arc[0]}")
            table.column(name, width=55, anchor="center", stretch=False)
        for vertex, row in zip(vertices, matrix):
            table.insert("", "end", values=[f"{row_prefix}{vertex}"] + row)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=table.xview)
        table.config(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        ttk.Label(frame, text="+1 — начало; −1 — конец; 2 — петля").grid(
            row=2, column=0, sticky="w", pady=6
        )
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

    def draw_graphs(self):
        self.canvas.delete("all")
        if not self.data:
            return
        width = max(self.canvas.winfo_width(), 600)
        height = max(self.canvas.winfo_height(), 400)
        border = width * 0.58
        self.canvas.create_line(border, 10, border, height - 10, fill="#cbd5e1")
        self.canvas.create_text(border / 2, 22, text="Исходный граф",
                                font=("Arial", 12, "bold"))
        self.canvas.create_text(border + (width - border) / 2, 22,
                                text="Граф подсистем", font=("Arial", 12, "bold"))

        vertex_colors = {}
        for i, subsystem in enumerate(self.data["subsystems"]):
            for vertex in subsystem:
                vertex_colors[vertex] = COLORS[i % len(COLORS)]

        old_arcs = [(a[1], a[2], f"e{a[0]}") for a in self.data["arcs"]]
        self.draw_graph(self.data["vertices"], old_arcs, 10, 42, border - 20,
                        height - 52, lambda v: str(v), lambda v: vertex_colors[v])
        subsystem_numbers = list(range(1, len(self.data["subsystems"]) + 1))
        new_arcs = [(a[1], a[2], f"E{a[0]}") for a in self.data["new_arcs"]]
        self.draw_graph(subsystem_numbers, new_arcs, border + 10, 42,
                        width - border - 20, height - 52, lambda v: f"S{v}",
                        lambda v: COLORS[(v - 1) % len(COLORS)])

    def draw_graph(self, vertices, arcs, x, y, width, height, label, color):
        if not vertices:
            return
        cx, cy = x + width / 2, y + height / 2
        radius = max(40, min(width, height) / 2 - 45)
        if len(vertices) == 1:
            positions = {vertices[0]: (cx, cy)}
        else:
            positions = {}
            for i, vertex in enumerate(vertices):
                angle = -math.pi / 2 + 2 * math.pi * i / len(vertices)
                positions[vertex] = (cx + radius * math.cos(angle),
                                     cy + radius * math.sin(angle))

        for start, end, arc_name in arcs:
            x1, y1 = positions[start]
            x2, y2 = positions[end]
            if start == end:
                self.canvas.create_arc(x1 - 20, y1 - 38, x1 + 20, y1 - 4,
                                       start=15, extent=300, style="arc", width=2)
                self.canvas.create_polygon(x1 + 17, y1 - 12, x1 + 9, y1 - 16,
                                           x1 + 15, y1 - 21, fill="#64748b")
                self.canvas.create_text(x1 + 25, y1 - 31, text=arc_name)
                continue
            dx, dy = x2 - x1, y2 - y1
            distance = math.hypot(dx, dy) or 1
            ux, uy = dx / distance, dy / distance
            ax, ay = x1 + ux * 20, y1 + uy * 20
            bx, by = x2 - ux * 20, y2 - uy * 20
            self.canvas.create_line(ax, ay, bx, by, arrow="last", width=2,
                                    fill="#64748b", arrowshape=(10, 12, 5))
            self.canvas.create_text((ax + bx) / 2 - uy * 10,
                                    (ay + by) / 2 + ux * 10, text=arc_name)

        for vertex in vertices:
            px, py = positions[vertex]
            self.canvas.create_oval(px - 20, py - 20, px + 20, py + 20,
                                    fill=color(vertex), outline="white", width=2)
            self.canvas.create_text(px, py, text=label(vertex), fill="white",
                                    font=("Arial", 10, "bold"))

    def load_example(self):
        self.input.delete("1.0", "end")
        self.input.insert("1.0", EXAMPLE)
        self.calculate()

    def clear(self):
        self.input.delete("1.0", "end")
        self.input.focus_set()

    def save(self):
        if not self.data:
            return
        filename = filedialog.asksaveasfilename(
            parent=self, defaultextension=".txt", initialfile="report.txt",
            filetypes=[("Текстовый файл", "*.txt"), ("Все файлы", "*.*")]
        )
        if filename:
            try:
                Path(filename).write_text(make_report(self.data), encoding="utf-8")
                self.status.set(f"Отчёт сохранён: {filename}")
            except OSError as error:
                messagebox.showerror("Ошибка сохранения", str(error), parent=self)

    def help(self):
        messagebox.showinfo(
            "Справка",
            "Введите G⁺ построчно, например:\n"
            "G+(1) = {2, 3}\n2: 1 4\n3 -> {}\n\n"
            "Подсистемы определяются как S(i) = R(i) ∩ Q(i).\n"
            "Запуск расчёта с клавиатуры: Ctrl+Enter.", parent=self,
        )


if __name__ == "__main__":
    GraphApp().mainloop()
