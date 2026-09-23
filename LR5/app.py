import re
import tkinter as tk
from tkinter import messagebox


EXAMPLE = """G-(1) = {}
G-(2) = {1}
G-(3) = {1, 2}
G-(4) = {2, 3}
G-(5) = {3, 4, 6}
G-(6) = {1, 5}"""


def read_graph(text):
    """Читает множество левых инциденций G-."""
    graph = {}
    pattern = re.compile(
        r"^\s*(?:G\s*-\s*\(\s*)?(\d+)(?:\s*\))?\s*(?:=|:|<-|←)\s*(.*?)\s*$",
        re.I,
    )

    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        found = pattern.match(line)
        if not found:
            raise ValueError(
                f"Строка {line_number}: используйте формат G-(1) = {{2, 3}}"
            )

        vertex = int(found.group(1))
        if vertex < 1:
            raise ValueError("Номера вершин должны быть положительными")
        if vertex in graph:
            raise ValueError(f"Вершина {vertex} указана дважды")

        value = found.group(2).strip().strip("{}[]() ")
        if value.lower() in ("", "ø", "∅", "-", "нет", "0"):
            graph[vertex] = []
            continue

        predecessors = []
        for word in re.split(r"[\s,;]+", value):
            if not word.isdigit() or int(word) < 1:
                raise ValueError(
                    f"Строка {line_number}: «{word}» не является номером вершины"
                )
            number = int(word)
            if number == vertex:
                raise ValueError(f"Петля в вершине {vertex} не допускается")
            if number not in predecessors:
                predecessors.append(number)
        graph[vertex] = sorted(predecessors)

    if not graph:
        raise ValueError("Введите хотя бы две вершины")

    # Добавляем вершины, которые встретились только в правой части.
    all_vertices = set(graph)
    for predecessors in graph.values():
        all_vertices.update(predecessors)
    for vertex in all_vertices:
        graph.setdefault(vertex, [])

    if len(graph) < 2:
        raise ValueError("Для расчёта K в графе должно быть не менее двух вершин")
    return dict(sorted(graph.items()))


def is_connected(vertices, edges):
    """Проверяет связность неориентированного графа."""
    neighbours = {vertex: [] for vertex in vertices}
    for first, second in edges:
        neighbours[first].append(second)
        neighbours[second].append(first)

    visited = {vertices[0]}
    stack = [vertices[0]]
    while stack:
        vertex = stack.pop()
        for neighbour in neighbours[vertex]:
            if neighbour not in visited:
                visited.add(neighbour)
                stack.append(neighbour)
    return len(visited) == len(vertices)


def analyze(text):
    graph = read_graph(text)
    vertices = list(graph)

    # В G-(i) записаны вершины, из которых дуги входят в i.
    arcs = []
    for end in vertices:
        for start in graph[end]:
            arcs.append((start, end))

    # Для расчёта показателей направление дуг не учитывается.
    edges = set()
    for start, end in arcs:
        edges.add(tuple(sorted((start, end))))
    edges = sorted(edges)

    degrees = {vertex: 0 for vertex in vertices}
    for first, second in edges:
        degrees[first] += 1
        degrees[second] += 1

    n = len(vertices)
    m = len(edges)
    average_degree = 2 * m / n
    redundancy = m / (n - 1) - 1
    epsilon_squared = sum(
        (degrees[vertex] - average_degree) ** 2 for vertex in vertices
    )

    return {
        "vertices": vertices,
        "arcs": arcs,
        "edges": edges,
        "degrees": degrees,
        "n": n,
        "m": m,
        "average_degree": average_degree,
        "redundancy": redundancy,
        "epsilon_squared": epsilon_squared,
        "connected": is_connected(vertices, edges),
    }


def number(value):
    """Красиво выводит целые и дробные значения."""
    if abs(value - round(value)) < 0.0000001:
        return str(round(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def make_report(data):
    lines = [
        "АНАЛИЗ КАЧЕСТВА СТРУКТУРЫ СИСТЕМЫ",
        "",
        "Ориентированный граф преобразован в неориентированный:",
        "направления дуг не учитываются, встречные дуги объединяются.",
        "",
        f"Количество вершин: n = {data['n']}",
        f"Количество дуг исходного графа: {len(data['arcs'])}",
        f"Количество рёбер: m = {data['m']}",
        f"Граф связный: {'да' if data['connected'] else 'нет'}",
        "",
        "Рёбра неориентированного графа:",
    ]

    if data["edges"]:
        lines.append("  " + ", ".join(
            f"({first}, {second})" for first, second in data["edges"]
        ))
    else:
        lines.append("  Рёбер нет")

    lines += ["", "Степени вершин:"]
    for vertex in data["vertices"]:
        lines.append(f"  ρ{vertex} = {data['degrees'][vertex]}")

    lines += [
        "",
        "1. Структурная избыточность:",
        "   K = m / (n - 1) - 1",
        f"   K = {data['m']} / ({data['n']} - 1) - 1 = "
        f"{number(data['redundancy'])}",
        "",
        "2. Неравномерность распределения связей:",
        "   ρ̅ = 2m / n",
        f"   ρ̅ = 2 · {data['m']} / {data['n']} = "
        f"{number(data['average_degree'])}",
        "   ε² = Σ(ρᵢ - ρ̅)²",
        f"   ε² = {number(data['epsilon_squared'])}",
        "",
    ]

    if data["redundancy"] > 0:
        lines.append("Вывод: структура имеет избыточные связи (K > 0).")
    elif abs(data["redundancy"]) < 0.0000001:
        lines.append("Вывод: структура имеет минимальное число связей (K = 0).")
    else:
        lines.append("Вывод: структуре недостаточно связей (K < 0).")

    if abs(data["epsilon_squared"]) < 0.0000001:
        lines.append("Связи распределены по вершинам равномерно (ε² = 0).")
    else:
        lines.append("Связи распределены по вершинам неравномерно (ε² > 0).")
    return "\n".join(lines)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Лабораторная работа №5")
        self.geometry("1050x650")
        self.minsize(800, 500)

        tk.Label(
            self,
            text="Анализ качества структуры системы",
            font=("Arial", 16, "bold"),
            pady=12,
        ).pack()

        panels = tk.PanedWindow(self, orient="horizontal", sashwidth=5)
        panels.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        left = tk.Frame(panels)
        right = tk.Frame(panels)
        panels.add(left, minsize=270)
        panels.add(right, minsize=450)

        tk.Label(left, text="Множество левых инциденций G⁻",
                 font=("Arial", 11, "bold")).pack(anchor="w")
        tk.Label(left, text="Пример: G-(3) = {1, 2}", pady=5).pack(anchor="w")
        self.input_text = tk.Text(left, font=("Courier New", 11), undo=True)
        self.input_text.pack(fill="both", expand=True)

        buttons = tk.Frame(left)
        buttons.pack(fill="x", pady=(8, 0))
        tk.Button(buttons, text="Рассчитать", command=self.calculate).pack(
            fill="x", pady=(0, 4)
        )
        tk.Button(buttons, text="Пример", command=self.load_example).pack(
            side="left", fill="x", expand=True
        )
        tk.Button(buttons, text="Очистить", command=self.clear).pack(
            side="left", fill="x", expand=True, padx=(4, 0)
        )

        tk.Label(right, text="Результаты расчёта",
                 font=("Arial", 11, "bold")).pack(anchor="w")
        result_frame = tk.Frame(right)
        result_frame.pack(fill="both", expand=True, pady=(5, 0))
        self.output_text = tk.Text(
            result_frame, font=("Courier New", 10), wrap="word", state="disabled"
        )
        scrollbar = tk.Scrollbar(result_frame, command=self.output_text.yview)
        self.output_text.config(yscrollcommand=scrollbar.set)
        self.output_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status = tk.StringVar(value="Готово")
        tk.Label(self, textvariable=self.status, relief="sunken",
                 anchor="w", padx=5).pack(fill="x")

        self.bind("<Control-Return>", lambda event: self.calculate())
        self.load_example()

    def calculate(self):
        try:
            data = analyze(self.input_text.get("1.0", "end"))
        except ValueError as error:
            self.status.set("Ошибка ввода")
            messagebox.showerror("Ошибка", str(error), parent=self)
            return

        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", make_report(data))
        self.output_text.config(state="disabled")
        self.status.set(
            f"Вершин: {data['n']}; рёбер: {data['m']}; "
            f"K = {number(data['redundancy'])}; "
            f"ε² = {number(data['epsilon_squared'])}"
        )

    def load_example(self):
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", EXAMPLE)
        self.calculate()

    def clear(self):
        self.input_text.delete("1.0", "end")
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")
        self.status.set("Введите граф")
        self.input_text.focus_set()


if __name__ == "__main__":
    App().mainloop()
