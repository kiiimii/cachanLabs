from collections import deque
from math import inf
import tkinter as tk
from tkinter import messagebox


# Пример матрицы расстояний. Ноль вне диагонали означает, что ребра нет.
EXAMPLE = [
    [0, 7, 9, 0, 0, 14],
    [7, 0, 10, 15, 0, 0],
    [9, 10, 0, 11, 0, 2],
    [0, 15, 11, 0, 6, 0],
    [0, 0, 0, 6, 0, 9],
    [14, 0, 2, 0, 9, 0],
]


def levit(matrix, start):
    """Находит расстояния от вершины start до всех остальных вершин."""
    n = len(matrix)
    distance = [inf] * n
    distance[start] = 0

    # state: 0 - еще не посещена, 1 - в очереди, 2 - уже обработана
    state = [0] * n
    state[start] = 1
    queue = deque([start])
    edge_count = [0] * n

    while queue:
        vertex = queue.popleft()
        state[vertex] = 2

        for neighbour in range(n):
            weight = matrix[vertex][neighbour]
            if weight == inf:
                continue

            new_distance = distance[vertex] + weight
            if new_distance >= distance[neighbour]:
                continue

            distance[neighbour] = new_distance
            edge_count[neighbour] = edge_count[vertex] + 1
            if edge_count[neighbour] >= n:
                raise ValueError("В графе есть цикл отрицательного веса")

            if state[neighbour] == 0:
                queue.append(neighbour)
                state[neighbour] = 1
            elif state[neighbour] == 2:
                queue.appendleft(neighbour)
                state[neighbour] = 1

    return distance


def shortest_path_matrix(matrix):
    """Строит матрицу кратчайших расстояний U."""
    return [levit(matrix, start) for start in range(len(matrix))]


def parse_matrix(text):
    """Преобразует текст из поля ввода в квадратную матрицу."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Введите матрицу расстояний")

    n = len(lines)
    matrix = []
    for i, line in enumerate(lines):
        words = line.replace(",", ".").split()
        if len(words) != n:
            raise ValueError(
                f"В строке {i + 1} должно быть {n} элементов, сейчас {len(words)}"
            )

        row = []
        for j, word in enumerate(words):
            if word.lower() in ("inf", "infinity", "-", "∞"):
                row.append(inf)
            else:
                try:
                    value = float(word)
                except ValueError:
                    raise ValueError(
                        f"Элемент «{word}» в строке {i + 1} не является числом"
                    )
                row.append(inf if i != j and value == 0 else value)
        matrix.append(row)
    return matrix


def matrix_to_text(matrix):
    """Преобразует матрицу в текст для вывода на экран."""
    lines = []
    for row in matrix:
        values = []
        for value in row:
            if value == inf:
                values.append("∞")
            elif value == int(value):
                values.append(str(int(value)))
            else:
                values.append(str(value))
        lines.append(" ".join(f"{value:>7}" for value in values))
    return "\n".join(lines)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Алгоритм Левита")
        self.geometry("950x570")
        self.minsize(750, 450)

        tk.Label(
            self,
            text="Поиск кратчайших путей алгоритмом Левита",
            font=("Arial", 16, "bold"),
            pady=12,
        ).pack()

        tk.Label(
            self,
            text=("Введите квадратную матрицу. Элементы разделяются пробелами. "
                  "0 вне диагонали, inf, ∞ или - означают отсутствие ребра."),
        ).pack(padx=10)

        fields = tk.Frame(self)
        fields.pack(fill="both", expand=True, padx=12, pady=10)

        left = tk.Frame(fields)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(left, text="Матрица расстояний D", font=("Arial", 11, "bold")).pack()
        self.input_text = tk.Text(left, font=("Courier New", 12), wrap="none")
        self.input_text.pack(fill="both", expand=True, pady=(6, 0))

        right = tk.Frame(fields)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        tk.Label(right, text="Матрица кратчайших путей U",
                 font=("Arial", 11, "bold")).pack()
        self.output_text = tk.Text(
            right, font=("Courier New", 12), wrap="none", state="disabled"
        )
        self.output_text.pack(fill="both", expand=True, pady=(6, 0))

        buttons = tk.Frame(self)
        buttons.pack(pady=(0, 12))
        tk.Button(buttons, text="Рассчитать", width=16,
                  command=self.calculate).pack(side="left", padx=5)
        tk.Button(buttons, text="Загрузить пример", width=16,
                  command=self.load_example).pack(side="left", padx=5)
        tk.Button(buttons, text="Очистить", width=16,
                  command=self.clear).pack(side="left", padx=5)

        self.bind("<Control-Return>", lambda event: self.calculate())
        self.load_example()

    def calculate(self):
        try:
            matrix = parse_matrix(self.input_text.get("1.0", "end"))
            result = shortest_path_matrix(matrix)
        except ValueError as error:
            messagebox.showerror("Ошибка", str(error), parent=self)
            return

        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", matrix_to_text(result))
        self.output_text.config(state="disabled")

    def load_example(self):
        self.input_text.delete("1.0", "end")
        self.input_text.insert("1.0", matrix_to_text(EXAMPLE))
        self.calculate()

    def clear(self):
        self.input_text.delete("1.0", "end")
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")
        self.input_text.focus_set()


if __name__ == "__main__":
    App().mainloop()
