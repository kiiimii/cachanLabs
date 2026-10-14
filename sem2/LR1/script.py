#!/usr/bin/env python3
"""Послеоптимизационный анализ задачи объёмного планирования.

Стандартная модель:

    max F = c[0] * x[0] + ... + c[n-1] * x[n-1]
    A * x <= b, x >= 0.

Программа не требует сторонних библиотек.  Она решает задачу симплекс-методом,
а затем по оптимальному базису находит теневые цены и интервалы устойчивости.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


EPS = 1e-9
INF = float("inf")


class PlanningError(ValueError):
    """Ошибка в исходных данных или математической модели."""


@dataclass
class Model:
    product_names: list[str]
    resource_names: list[str]
    profit: list[float]
    consumption: list[list[float]]
    stock: list[float]

    def validate(self) -> None:
        n = len(self.profit)
        m = len(self.stock)
        if n == 0 or m == 0:
            raise PlanningError("Нужен хотя бы один продукт и один ресурс.")
        if len(self.product_names) != n:
            raise PlanningError("Число названий продуктов не совпадает с числом прибылей.")
        if len(self.resource_names) != m or len(self.consumption) != m:
            raise PlanningError("Число ресурсов не согласовано с матрицей и запасами.")
        if any(len(row) != n for row in self.consumption):
            raise PlanningError("В каждой строке матрицы должно быть по одному числу на продукт.")
        values = self.profit + self.stock + [v for row in self.consumption for v in row]
        if any(not math.isfinite(v) for v in values):
            raise PlanningError("Все числа должны быть конечными.")
        if any(v < 0 for v in self.stock):
            raise PlanningError("В стандартной постановке запасы ресурсов неотрицательны.")
        if any(v < 0 for row in self.consumption for v in row):
            raise PlanningError("Нормы расхода в стандартной постановке неотрицательны.")


@dataclass
class Solution:
    plan: list[float]
    objective: float
    slacks: list[float]
    shadow_prices: list[float]
    reduced_costs: list[float]
    basis: list[int]
    rhs_ranges: list[tuple[float, float]]
    profit_ranges: list[tuple[float, float]]
    iterations: int
    alternate_optimum: bool


def _solve_linear(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    """Решить квадратную СЛАУ методом Гаусса с частичным выбором главного элемента."""
    n = len(vector)
    augmented = [list(map(float, matrix[i])) + [float(vector[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) <= EPS:
            raise PlanningError("Вырожденный базис: анализ устойчивости невозможен.")
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        divisor = augmented[col][col]
        augmented[col] = [value / divisor for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            if abs(factor) > EPS:
                augmented[row] = [
                    augmented[row][j] - factor * augmented[col][j] for j in range(n + 1)
                ]
    return [augmented[i][-1] for i in range(n)]


def _transpose(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    return [list(column) for column in zip(*matrix)]


def solve(model: Model) -> Solution:
    """Решить LP и выполнить анализ устойчивости найденного оптимального базиса."""
    model.validate()
    a, b, c = model.consumption, model.stock, model.profit
    m, n = len(b), len(c)
    total = n + m

    # Tableau: строки ограничений имеют вид x_B + T*x_N = rhs.
    tableau = []
    for i in range(m):
        tableau.append(list(a[i]) + [1.0 if i == j else 0.0 for j in range(m)] + [b[i]])
    basis = [n + i for i in range(m)]
    costs = list(c) + [0.0] * m
    iterations = 0

    while True:
        cb = [costs[index] for index in basis]
        reduced = [
            costs[j] - sum(cb[i] * tableau[i][j] for i in range(m)) for j in range(total)
        ]
        entering = next((j for j in range(total) if j not in basis and reduced[j] > EPS), None)
        if entering is None:
            break

        candidates = [
            (tableau[i][-1] / tableau[i][entering], basis[i], i)
            for i in range(m)
            if tableau[i][entering] > EPS
        ]
        if not candidates:
            raise PlanningError("Целевая функция не ограничена сверху.")
        _, _, leaving_row = min(candidates)
        pivot = tableau[leaving_row][entering]
        tableau[leaving_row] = [value / pivot for value in tableau[leaving_row]]
        for i in range(m):
            if i == leaving_row:
                continue
            factor = tableau[i][entering]
            if abs(factor) > EPS:
                tableau[i] = [
                    tableau[i][j] - factor * tableau[leaving_row][j]
                    for j in range(total + 1)
                ]
        basis[leaving_row] = entering
        iterations += 1
        if iterations > 10000:
            raise PlanningError("Превышен предел итераций симплекс-метода.")

    full_plan = [0.0] * total
    for row, variable in enumerate(basis):
        full_plan[variable] = _clean(tableau[row][-1])
    objective = _clean(sum(c[j] * full_plan[j] for j in range(n)))

    # Исходная расширенная матрица [A | I] и матрица текущего базиса B.
    extended = [list(a[i]) + [1.0 if i == j else 0.0 for j in range(m)] for i in range(m)]
    basis_matrix = [[extended[i][basis[col]] for col in range(m)] for i in range(m)]
    cb = [costs[index] for index in basis]
    shadow = [_clean(v) for v in _solve_linear(_transpose(basis_matrix), cb)]
    reduced = [
        _clean(costs[j] - sum(shadow[i] * extended[i][j] for i in range(m)))
        for j in range(total)
    ]

    # Интервалы для b_i: x_B(new) = x_B + delta * B^-1*e_i.
    rhs_ranges: list[tuple[float, float]] = []
    basic_values = [tableau[row][-1] for row in range(m)]
    for resource in range(m):
        direction = [tableau[row][n + resource] for row in range(m)]
        low, high = -INF, INF
        for value, coefficient in zip(basic_values, direction):
            if coefficient > EPS:
                low = max(low, -value / coefficient)
            elif coefficient < -EPS:
                high = min(high, -value / coefficient)
        rhs_ranges.append((_clean_bound(b[resource] + low), _clean_bound(b[resource] + high)))

    # Интервалы для c_j, при которых данный базис остаётся оптимальным.
    nonbasic = [j for j in range(total) if j not in basis]
    profit_ranges: list[tuple[float, float]] = []
    for product in range(n):
        low, high = -INF, INF  # границы изменения delta
        if product not in basis:
            high = -reduced[product]
        else:
            row = basis.index(product)
            for j in nonbasic:
                coefficient = tableau[row][j]  # (B^-1*A_j)_row
                if coefficient > EPS:
                    low = max(low, reduced[j] / coefficient)
                elif coefficient < -EPS:
                    high = min(high, reduced[j] / coefficient)
        profit_ranges.append((_clean_bound(c[product] + low), _clean_bound(c[product] + high)))

    alternate = any(abs(reduced[j]) <= 1e-7 for j in range(n) if j not in basis)
    return Solution(
        plan=[_clean(v) for v in full_plan[:n]],
        objective=objective,
        slacks=[_clean(v) for v in full_plan[n:]],
        shadow_prices=shadow,
        reduced_costs=[_clean(v) for v in reduced[:n]],
        basis=basis,
        rhs_ranges=rhs_ranges,
        profit_ranges=profit_ranges,
        iterations=iterations,
        alternate_optimum=alternate,
    )


def _clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-8 else value


def _clean_bound(value: float) -> float:
    if math.isinf(value):
        return value
    return _clean(value)


def _number(value: float) -> str:
    if value == INF:
        return "+∞"
    if value == -INF:
        return "−∞"
    return f"{value:.6g}"


def _interval(bounds: tuple[float, float]) -> str:
    return f"[{_number(bounds[0])}; {_number(bounds[1])}]"


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    data = [[str(item) for item in row] for row in rows]
    all_rows = [list(headers)] + data
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    line = "-+-".join("-" * width for width in widths)
    rendered = [" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))), line]
    rendered.extend(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))) for row in data)
    return "\n".join(rendered)


def print_report(model: Model, result: Solution) -> None:
    print("\nОПТИМАЛЬНЫЙ ОБЪЁМНЫЙ ПЛАН")
    print(_table(
        ("Продукт", "Объём x", "Прибыль/ед.", "Вклад в результат"),
        ((name, _number(x), _number(p), _number(x * p))
         for name, x, p in zip(model.product_names, result.plan, model.profit)),
    ))
    print(f"\nМаксимальное значение целевой функции: {_number(result.objective)}")
    print(f"Итераций симплекс-метода: {result.iterations}")

    print("\nПОСЛЕОПТИМИЗАЦИОННЫЙ АНАЛИЗ РЕСУРСОВ")
    resource_rows = []
    for i, name in enumerate(model.resource_names):
        used = model.stock[i] - result.slacks[i]
        status = "дефицитный" if result.slacks[i] <= 1e-7 else "есть резерв"
        resource_rows.append((
            name, _number(model.stock[i]), _number(used), _number(result.slacks[i]),
            status, _number(result.shadow_prices[i]), _interval(result.rhs_ranges[i]),
        ))
    print(_table(
        ("Ресурс", "Запас", "Расход", "Остаток", "Статус", "Теневая цена", "Интервал запаса"),
        resource_rows,
    ))

    print("\nУСТОЙЧИВОСТЬ ПРИБЫЛИ ПРОДУКТОВ")
    print(_table(
        ("Продукт", "Прибыль", "Приведённая оценка", "Допустимый интервал"),
        ((name, _number(model.profit[i]), _number(result.reduced_costs[i]),
          _interval(result.profit_ranges[i])) for i, name in enumerate(model.product_names)),
    ))
    print("\nПояснение:")
    print("  • Теневая цена показывает изменение максимальной прибыли при добавлении")
    print("    одной единицы ресурса — пока его запас остаётся в указанном интервале.")
    print("  • Отрицательная приведённая оценка неприменяемого продукта показывает,")
    print("    насколько должна вырасти его прибыль, чтобы выпуск стал выгодным.")
    print("  • В пределах интервалов сохраняется текущий оптимальный базис; одновременное")
    print("    изменение нескольких параметров требует повторного решения задачи.")
    if result.alternate_optimum:
        print("  • Обнаружен альтернативный оптимум: существует другой план с той же прибылью.")


def demo_model() -> Model:
    return Model(
        product_names=["Изделие A", "Изделие B", "Изделие C"],
        resource_names=["Оборудование, ч", "Сырьё, кг", "Труд, чел.-ч"],
        profit=[40.0, 35.0, 20.0],
        consumption=[
            [2.0, 1.0, 1.0],
            [1.0, 2.0, 1.0],
            [1.0, 1.0, 2.0],
        ],
        stock=[100.0, 80.0, 90.0],
    )


def _read_positive_int(prompt: str) -> int:
    while True:
        try:
            value = int(input(prompt))
            if value > 0:
                return value
        except ValueError:
            pass
        print("Введите положительное целое число.")


def _read_float(prompt: str, nonnegative: bool = False) -> float:
    while True:
        raw = input(prompt).strip().replace(",", ".")
        try:
            value = float(raw)
            if math.isfinite(value) and (not nonnegative or value >= 0):
                return value
        except ValueError:
            pass
        suffix = " неотрицательное" if nonnegative else ""
        print(f"Введите корректное{suffix} число.")


def input_model() -> Model:
    print("\nВведите параметры модели max(c·x), A·x ≤ b, x ≥ 0.")
    n = _read_positive_int("Количество видов продукции: ")
    m = _read_positive_int("Количество ресурсов: ")
    products, profit = [], []
    for j in range(n):
        name = input(f"Название продукта {j + 1} [Продукт {j + 1}]: ").strip()
        products.append(name or f"Продукт {j + 1}")
        profit.append(_read_float(f"Прибыль от единицы «{products[-1]}»: "))
    resources, stock, matrix = [], [], []
    for i in range(m):
        name = input(f"\nНазвание ресурса {i + 1} [Ресурс {i + 1}]: ").strip()
        resources.append(name or f"Ресурс {i + 1}")
        stock.append(_read_float(f"Доступный запас «{resources[-1]}»: ", nonnegative=True))
        row = []
        for product in products:
            row.append(_read_float(
                f"Расход «{resources[-1]}» на единицу «{product}»: ", nonnegative=True
            ))
        matrix.append(row)
    return Model(products, resources, profit, matrix, stock)


def load_json(path: Path) -> Model:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        model = Model(
            product_names=list(data["products"]),
            resource_names=list(data["resources"]),
            profit=[float(v) for v in data["profit"]],
            consumption=[[float(v) for v in row] for row in data["consumption"]],
            stock=[float(v) for v in data["stock"]],
        )
        model.validate()
        return model
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PlanningError(f"Не удалось прочитать модель из {path}: {error}") from error


def save_json(model: Model, path: Path) -> None:
    """Сохранить модель в переносимом JSON-формате."""
    model.validate()
    data = {
        "products": model.product_names,
        "resources": model.resource_names,
        "profit": model.profit,
        "consumption": model.consumption,
        "stock": model.stock,
    }
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as error:
        raise PlanningError(f"Не удалось сохранить модель в {path}: {error}") from error


def launch_gui(initial_model: Model | None = None) -> bool:
    """Запустить графический интерфейс. Вернуть False, если Tk недоступен."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        root = tk.Tk()
    except (ImportError, RuntimeError) as error:
        print(f"Графический интерфейс недоступен: {error}", file=sys.stderr)
        return False
    except Exception as error:
        # В Linux без графической сессии Tk создаёт TclError.
        if error.__class__.__name__ == "TclError":
            print(f"Графический интерфейс недоступен: {error}", file=sys.stderr)
            return False
        raise

    root.title("Объёмное планирование — послеоптимизационный анализ")
    root.geometry("1120x760")
    root.minsize(900, 620)

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("Title.TLabel", font=("TkDefaultFont", 15, "bold"))
    style.configure("Heading.TLabel", font=("TkDefaultFont", 10, "bold"))
    style.configure("Accent.TButton", font=("TkDefaultFont", 10, "bold"))

    notebook = ttk.Notebook(root)
    input_tab = ttk.Frame(notebook, padding=12)
    result_tab = ttk.Frame(notebook, padding=12)
    notebook.add(input_tab, text="  Исходные данные  ")
    notebook.add(result_tab, text="  Результаты анализа  ")
    notebook.pack(fill="both", expand=True)

    top = ttk.Frame(input_tab)
    top.pack(fill="x", pady=(0, 10))
    ttk.Label(top, text="Задача объёмного планирования", style="Title.TLabel").pack(side="left")
    size_box = ttk.Frame(top)
    size_box.pack(side="right")
    ttk.Label(size_box, text="Продуктов:").grid(row=0, column=0, padx=(0, 4))
    product_count = tk.IntVar(value=3)
    ttk.Spinbox(size_box, from_=1, to=20, width=4, textvariable=product_count).grid(row=0, column=1)
    ttk.Label(size_box, text="Ресурсов:").grid(row=0, column=2, padx=(12, 4))
    resource_count = tk.IntVar(value=3)
    ttk.Spinbox(size_box, from_=1, to=20, width=4, textvariable=resource_count).grid(row=0, column=3)

    hint = ttk.Label(
        input_tab,
        text="Модель: максимизировать прибыль c·x при ограничениях A·x ≤ b, x ≥ 0",
        foreground="#4b5563",
    )
    hint.pack(anchor="w", pady=(0, 8))

    canvas_box = ttk.Frame(input_tab)
    canvas_box.pack(fill="both", expand=True)
    canvas = tk.Canvas(canvas_box, highlightthickness=0)
    y_scroll = ttk.Scrollbar(canvas_box, orient="vertical", command=canvas.yview)
    x_scroll = ttk.Scrollbar(canvas_box, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    y_scroll.pack(side="right", fill="y")
    x_scroll.pack(side="bottom", fill="x")
    canvas.pack(side="left", fill="both", expand=True)
    grid_frame = ttk.Frame(canvas, padding=6)
    window_id = canvas.create_window((0, 0), window=grid_frame, anchor="nw")
    grid_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind(
        "<Configure>",
        lambda event: canvas.itemconfigure(window_id, width=max(event.width, grid_frame.winfo_reqwidth())),
    )

    product_entries: list[object] = []
    profit_entries: list[object] = []
    resource_entries: list[object] = []
    stock_entries: list[object] = []
    consumption_entries: list[list[object]] = []

    def put(entry: object, value: object) -> None:
        entry.delete(0, tk.END)
        entry.insert(0, str(value))

    def rebuild(model: Model | None = None) -> None:
        nonlocal product_entries, profit_entries, resource_entries, stock_entries, consumption_entries
        if model is not None:
            product_count.set(len(model.product_names))
            resource_count.set(len(model.resource_names))
        try:
            n, m = int(product_count.get()), int(resource_count.get())
            if not (1 <= n <= 20 and 1 <= m <= 20):
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Некорректный размер", "Введите от 1 до 20 продуктов и ресурсов.")
            return

        for child in grid_frame.winfo_children():
            child.destroy()
        product_entries, profit_entries = [], []
        resource_entries, stock_entries, consumption_entries = [], [], []

        ttk.Label(grid_frame, text="Ресурс / продукт", style="Heading.TLabel").grid(
            row=0, column=0, padx=4, pady=5, sticky="ew"
        )
        for j in range(n):
            entry = ttk.Entry(grid_frame, width=15, justify="center")
            entry.grid(row=0, column=j + 1, padx=3, pady=3, sticky="ew")
            put(entry, model.product_names[j] if model else f"Продукт {j + 1}")
            product_entries.append(entry)
        ttk.Label(grid_frame, text="Запас b", style="Heading.TLabel").grid(
            row=0, column=n + 1, padx=4, pady=5
        )

        ttk.Label(grid_frame, text="Прибыль c", style="Heading.TLabel").grid(
            row=1, column=0, padx=4, pady=3, sticky="e"
        )
        for j in range(n):
            entry = ttk.Entry(grid_frame, width=12, justify="center")
            entry.grid(row=1, column=j + 1, padx=3, pady=3)
            put(entry, model.profit[j] if model else 0)
            profit_entries.append(entry)
        ttk.Separator(grid_frame, orient="horizontal").grid(
            row=2, column=0, columnspan=n + 2, pady=5, sticky="ew"
        )

        for i in range(m):
            name_entry = ttk.Entry(grid_frame, width=20)
            name_entry.grid(row=i + 3, column=0, padx=3, pady=3, sticky="ew")
            put(name_entry, model.resource_names[i] if model else f"Ресурс {i + 1}")
            resource_entries.append(name_entry)
            row_entries = []
            for j in range(n):
                entry = ttk.Entry(grid_frame, width=12, justify="center")
                entry.grid(row=i + 3, column=j + 1, padx=3, pady=3)
                put(entry, model.consumption[i][j] if model else 0)
                row_entries.append(entry)
            consumption_entries.append(row_entries)
            stock_entry = ttk.Entry(grid_frame, width=12, justify="center")
            stock_entry.grid(row=i + 3, column=n + 1, padx=3, pady=3)
            put(stock_entry, model.stock[i] if model else 0)
            stock_entries.append(stock_entry)
        for column in range(n + 2):
            grid_frame.columnconfigure(column, weight=1 if 0 < column <= n else 0)

    def parse_number(entry: object, field: str, nonnegative: bool = False) -> float:
        raw = entry.get().strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError as error:
            raise PlanningError(f"Поле «{field}» должно содержать число.") from error
        if not math.isfinite(value) or (nonnegative and value < 0):
            condition = "неотрицательное конечное число" if nonnegative else "конечное число"
            raise PlanningError(f"Поле «{field}» должно содержать {condition}.")
        return value

    def read_form() -> Model:
        products = [entry.get().strip() or f"Продукт {j + 1}" for j, entry in enumerate(product_entries)]
        resources = [entry.get().strip() or f"Ресурс {i + 1}" for i, entry in enumerate(resource_entries)]
        profits = [parse_number(entry, f"прибыль {products[j]}") for j, entry in enumerate(profit_entries)]
        stocks = [
            parse_number(entry, f"запас {resources[i]}", True) for i, entry in enumerate(stock_entries)
        ]
        matrix = [
            [
                parse_number(entry, f"расход {resources[i]} / {products[j]}", True)
                for j, entry in enumerate(row)
            ]
            for i, row in enumerate(consumption_entries)
        ]
        model = Model(products, resources, profits, matrix, stocks)
        model.validate()
        return model

    summary_var = tk.StringVar(value="Заполните исходные данные и нажмите «Рассчитать».")
    ttk.Label(result_tab, text="Результаты оптимизации", style="Title.TLabel").pack(anchor="w")
    ttk.Label(result_tab, textvariable=summary_var, font=("TkDefaultFont", 11)).pack(
        anchor="w", pady=(6, 12)
    )

    plan_frame = ttk.LabelFrame(result_tab, text="Оптимальный план", padding=6)
    plan_frame.pack(fill="both", expand=True, pady=(0, 8))
    plan_tree = ttk.Treeview(
        plan_frame, columns=("volume", "profit", "contribution", "estimate", "range"),
        show="headings", height=7,
    )
    for key, title, width in (
        ("volume", "Объём", 90), ("profit", "Прибыль/ед.", 100),
        ("contribution", "Вклад", 100), ("estimate", "Приведённая оценка", 145),
        ("range", "Интервал прибыли", 150),
    ):
        plan_tree.heading(key, text=title)
        plan_tree.column(key, width=width, anchor="center")
    plan_tree.pack(fill="both", expand=True)

    resource_frame = ttk.LabelFrame(result_tab, text="Анализ ресурсов", padding=6)
    resource_frame.pack(fill="both", expand=True)
    resource_tree = ttk.Treeview(
        resource_frame,
        columns=("stock", "used", "rest", "status", "shadow", "range"),
        show="headings", height=7,
    )
    for key, title, width in (
        ("stock", "Запас", 75), ("used", "Расход", 75), ("rest", "Остаток", 75),
        ("status", "Статус", 105), ("shadow", "Теневая цена", 110),
        ("range", "Интервал запаса", 145),
    ):
        resource_tree.heading(key, text=title)
        resource_tree.column(key, width=width, anchor="center")
    resource_tree.pack(fill="both", expand=True)

    def clear_tree(tree: object) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def calculate() -> None:
        try:
            model = read_form()
            result = solve(model)
        except PlanningError as error:
            messagebox.showerror("Ошибка исходных данных", str(error))
            return
        clear_tree(plan_tree)
        clear_tree(resource_tree)
        for i, name in enumerate(model.product_names):
            plan_tree.insert("", "end", text=name, values=(
                _number(result.plan[i]), _number(model.profit[i]),
                _number(result.plan[i] * model.profit[i]), _number(result.reduced_costs[i]),
                _interval(result.profit_ranges[i]),
            ), tags=("active" if result.plan[i] > EPS else "inactive",))
        # Treeview with show=headings hides #0, so use the first displayed column for names.
        plan_tree.configure(show="tree headings")
        plan_tree.heading("#0", text="Продукт")
        plan_tree.column("#0", width=150, anchor="w")
        for i, name in enumerate(model.resource_names):
            used = model.stock[i] - result.slacks[i]
            status = "дефицитный" if result.slacks[i] <= 1e-7 else "есть резерв"
            resource_tree.insert("", "end", text=name, values=(
                _number(model.stock[i]), _number(used), _number(result.slacks[i]), status,
                _number(result.shadow_prices[i]), _interval(result.rhs_ranges[i]),
            ))
        resource_tree.configure(show="tree headings")
        resource_tree.heading("#0", text="Ресурс")
        resource_tree.column("#0", width=170, anchor="w")
        note = " Есть альтернативный оптимум." if result.alternate_optimum else ""
        summary_var.set(
            f"Максимальная прибыль: {_number(result.objective)}. "
            f"Итераций симплекс-метода: {result.iterations}.{note}"
        )
        notebook.select(result_tab)

    def load_from_file() -> None:
        filename = filedialog.askopenfilename(
            title="Открыть модель", filetypes=(("JSON", "*.json"), ("Все файлы", "*.*"))
        )
        if not filename:
            return
        try:
            rebuild(load_json(Path(filename)))
        except PlanningError as error:
            messagebox.showerror("Ошибка открытия", str(error))

    def save_to_file() -> None:
        try:
            model = read_form()
        except PlanningError as error:
            messagebox.showerror("Ошибка исходных данных", str(error))
            return
        filename = filedialog.asksaveasfilename(
            title="Сохранить модель", defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("Все файлы", "*.*")),
        )
        if filename:
            try:
                save_json(model, Path(filename))
            except PlanningError as error:
                messagebox.showerror("Ошибка сохранения", str(error))

    buttons = ttk.Frame(input_tab)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="Применить размер", command=rebuild).pack(side="left")
    ttk.Button(buttons, text="Демонстрационный пример", command=lambda: rebuild(demo_model())).pack(
        side="left", padx=6
    )
    ttk.Button(buttons, text="Открыть JSON", command=load_from_file).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Сохранить JSON", command=save_to_file).pack(side="left", padx=6)
    ttk.Button(buttons, text="Рассчитать", style="Accent.TButton", command=calculate).pack(side="right")

    plan_tree.tag_configure("inactive", foreground="#6b7280")
    rebuild(initial_model or demo_model())
    root.mainloop()
    return True


def run_self_test() -> None:
    result = solve(demo_model())
    assert abs(result.objective - 2300.0) < 1e-6
    assert all(abs(a - b) < 1e-6 for a, b in zip(result.plan, [40.0, 20.0, 0.0]))
    assert all(abs(a - b) < 1e-6 for a, b in zip(result.shadow_prices, [15.0, 10.0, 0.0]))

    simple = Model(["X"], ["R"], [3.0], [[2.0]], [8.0])
    one = solve(simple)
    assert abs(one.plan[0] - 4.0) < 1e-6 and abs(one.objective - 12.0) < 1e-6
    assert abs(one.shadow_prices[0] - 1.5) < 1e-6
    print("Самопроверка пройдена успешно.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Оптимизация объёмного плана и послеоптимизационный анализ."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--demo", action="store_true", help="решить встроенный демонстрационный пример")
    group.add_argument("--file", type=Path, metavar="MODEL.json", help="загрузить модель из JSON")
    group.add_argument("--self-test", action="store_true", help="выполнить автоматическую проверку")
    group.add_argument("--console", action="store_true", help="использовать текстовый интерфейс")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.self_test:
            run_self_test()
            return 0
        if args.demo:
            model = demo_model()
        elif args.file:
            model = load_json(args.file)
        elif not args.console and launch_gui():
            return 0
        elif not sys.stdin.isatty():
            # В перенаправленном запуске и без GUI не зависаем в ожидании ввода.
            model = demo_model()
            print("Используется демонстрационный пример в консольном режиме.")
        else:
            print("ПОСЛЕОПТИМИЗАЦИОННЫЙ АНАЛИЗ ОБЪЁМНОГО ПЛАНА")
            print("1 — ввести свои данные")
            print("2 — запустить демонстрационный пример")
            choice = input("Выберите режим [2]: ").strip()
            model = input_model() if choice == "1" else demo_model()
        print_report(model, solve(model))
        return 0
    except (PlanningError, KeyboardInterrupt) as error:
        message = "Работа прервана пользователем." if isinstance(error, KeyboardInterrupt) else str(error)
        print(f"\nОшибка: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
