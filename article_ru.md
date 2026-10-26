# Capability-based Security в Python на практике: PyIntents

> **Важно: историческая статья.** Актуальные ограничения статического анализа,
> модель доверия и API `IntentDispatcher` описаны в `README.md` и
> `docs/security.rst`. Для враждебного кода нужна OS-изоляция; предварительная
> проверка не обеспечивает транзакционность или откат эффектов.

Однажды, изучая просторы интернета, я нашел интересную идею — Capability-based Security. Это подход, при котором доступ к функции или ресурсу управляется через разрешения (capability). Я решил не распыляться на нее всю, а изучить конкретный термин — интенты (intents). Интенты (декларация намерений) — это декларативное объявление намерений, то есть условно, какие capabilities (возможности/права) понадобятся функции или модулю для работы.

И я загорелся идеей попробовать реализовать такой функционал в Python через библиотеку. Это отличный способ изучить паттерны и AST.

Python — динамичный и мощный, но эта мощь — источник небезопасности. Моя идея в том, что через декоратор функция декларирует, какие функции ей нужны, а в случае неразрешенных — блокировала бы вызов.

Идея жизнеспособная, это отлично ложится для реализации системы плагинов, проектирования AI-агентов или фреймворков для тестирования.

В этой статье я расскажу о capability-based security и попробуем решить дилемму: как дать функции только те возможности, которые ей нужны, и ничего больше?

---

Перед тем как начать, хочу показать, что у меня получилось. Вот у нас есть такой код:

```python
import os

from pyintents import IntentNamespace

main_namespace = IntentNamespace(
    uses=[print],   # декларация разрешенных функций
    recursive=True, # рекурсивное применение интентов к вызываемым функциям
    usemodule=True, # автоматическое разрешение вызова функций нашего модуля, для удобства
)


def inner() -> None:
    os.system("echo Inner")


def outer() -> None:
    print("Outer")
    inner()


@main_namespace.intent()
def func() -> None:
    print("Func")
    outer()


if __name__ == "__main__":
    try:
        func()
    except Exception as exc:
        print(f"Error: {exc}")
```

Данный код при вызове выведет всего одну строку: `Error: Function 'func -> outer -> inner' calls forbidden 'os.system'`.

В этой статье мы разберем, что и почему я делал для такого функционала.

# Capability-based Security: безопасность, основанная на возможностях

Давайте погрузимся для начала в матчасть, откуда пришла эта идея и как она устроена. Если описать одной фразой, то можно сказать, что это подход, при котором доступ к ресурсу (файлу, сетевому сокету, памяти, устройству) дается не по имени владельца (кто вы), а по наличию у вас в руках специального «ключа-пропуска» (capability), который нельзя подделать, украсть или использовать не по назначению.

Если говорить метафорами, то представим, что ресурсы — это квартиры. Вместо того чтобы пускать только хозяина (даже если он пришел без ключей), мы пускаем только тех, у кого есть ключ-карта. Capability — это объект и права, не просто строка или число, а ссылка на объект, который не может быть подделан.

Основные принципы этой системы — это отсутствие глобального пространства имен, нельзя запросить доступ «по праву рождению» (типа «я root», или «я родительский процесс»), принцип минимальных прав из коробки и передаваемость capability между компонентами.

Самой этой концепции уже много лет, все началось в 1966 году — Джек Деннис и Эрл Ван Хорн в MIT вводят саму концепцию capability. Они работали над многопользовательскими системами и хотели покончить с матрицами доступа, которые не масштабировались.

В 1970-х годах появились первые системы-пионеры:

![CAP computer (Cambridge) — аппаратная реализация capability, тегированная память](https://habrastorage.org/webt/1e/0c/e5/1e0ce5cbfdf10684e5c109e2728c8481.png)

Также были Hydra (CMU) — ОС, где защита строилась вокруг capability, а не вокруг ACL, и Multics — попытка построить кольца защиты, но без чистых capability.

![IBM System/38 (позже AS/400)](https://habrastorage.org/webt/5f/10/0f/5f100f31a43389ff20978e8ab170dfec.png)

IBM System/38 (позже AS/400) — единственная коммерческая архитектура с аппаратными capability на уровне микрокода. Каждый указатель был capability с тегом — прорыв, о котором все забыли.

В 90-е и в 2000-е появляется языковой подход, к примеру E Language и Joule.

А в 2010–2020-е этот концепт только рос. В 2013 Chrome получил изолированные вкладки через capabilities, а в 2016 появилась Fuchsia от Google — этакая ОС с capability-моделью от ядра до UI. К 2018 году в WebAssembly появились capabilities для браузерного кода.

Но что общего у всей этой истории с современным Python-разработчиком?

В классических системах capability — это физический объект или ссылка в памяти, которую нельзя подделать. Но в Python у нас нет аппаратной поддержки, мы не можем просто так раздавать «неподделываемые ключи» от `os.system`. К тому же Python — это язык с глобальным пространством имен, динамической диспетчеризацией и возможностью менять поведение в рантайме. Как же быть?

И тут мы приходим к концепции интентов (intents).

Если capability — это объект-ключ, то intent — это декларация намерения: «Я собираюсь использовать этот набор функций». То есть мы смещаем фокус на то, что заставляем декларировать используемые права в нашей функции. Проверка происходит не во время выполнения, а до него, через статический анализ AST.

В этом и заключается мое решение: вместо того чтобы раздавать capabilities в рантайме (что в Python почти невозможно безопасно), мы анализируем код функции и весь граф ее вызовов и сверяем с объявленными интентами.

Допустим, у нас есть функция:

```python
def dangerous():
    import os
    os.system("rm -rf /")
```

Мы, как разработчики, знаем, что она опасна. Но как это объяснить интерпретатору? Мы можем завернуть ее в декоратор и объявить интенты:

```python
from pyintents import IntentNamespace

ns = IntentNamespace(uses=[print])

@ns.intent()
def safe():
    print("Hello")           # ✅ Разрешено, print есть в uses


@ns.intent()
def unsafe():
    import os
    os.system("rm -rf /")    # ❌ Нарушение, os.system не в uses
```

Когда вызывается `unsafe()`, происходит следующее: PyIntents парсит исходный код с помощью модуля `ast`, строит дерево вызовов (Call Tree), включая все вложенные вызовы, проверяя каждый узел дерева, и если есть вызов функции, которого нет в `uses` или есть в `deny`, мы выбрасываем исключение.

То есть функция даже не выполнится, если будет найдено нарушение, — пан или пропал.

> Но почему именно интенты, а не что-то еще? В Python, конечно, уже есть похожие проекты, например RestrictedPython — выполняет код в ограниченной среде, подменяя глобальные переменные и запрещая опасные конструкции. Но это тяжеловесное решение, которое меняет семантику языка. А если самому, то вручную писать проверки и вставлять контекстные менеджеры — это неудобно и легко забывается.

# Разбор архитектуры

Достаточно теории, пришло время практики. Библиотека состоит из трех основных частей: интроспекция (сбор информации о коде), построение графа вызовов и движок политик.

Сама библиотека, кстати, доступна на [PyPI](https://pypi.org/project/pyintents/) для установки: `pip install pyintents`.

А полный исходный код доступен в [моем репозитории](https://github.com/alexeev-prog/pyintents/), в статье я не буду прикладывать весь код, а расскажу только о ключевых функциях и классах.

## introspect.py

Сердце библиотеки — модуль `introspect.py`. Он отвечает за парсинг исходного кода и извлечение информации о вызовах.

Вся магия начинается с `_get_function_ast` — функции, которая получает AST функции. Она принимает callable-объект, пытается получить его исходный код через `inspect.getsource`, нормализует отступы через `textwrap.dedent` и парсит через `ast.parse`. Если исходник недоступен (встроенная функция или C-расширение) — выбрасывается `IntentParseError`.

```python
def _get_function_ast(func: Callable[..., Any]) -> FunctionDefLike:
    func_name = getattr(
        func,
        "__qualname__",
        getattr(func, "__name__", repr(func)),
    )

    try:
        source = inspect.getsource(func)
    except (OSError, TypeError) as exc:
        raise IntentParseError(
            func_name,
            "source code is not available",
        ) from exc

    try:
        module = ast.parse(textwrap.dedent(source))
    except (SyntaxError, IndentationError) as exc:
        raise IntentParseError(
            func_name,
            f"invalid source: {exc}",
        ) from exc

    target_name = getattr(func, "__name__", None)

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target_name is None or node.name == target_name:
                return node

    raise IntentParseError(
        func_name,
        "function definition was not found in source",
    )
```

Функция сначала ищет определение в теле модуля, а если не находит — обходит всё дерево целиком через `ast.walk`. Это нужно для случаев, когда функция определена внутри условных конструкций или классов. Если исходный код недоступен — мы не можем анализировать функцию, и это честно сообщается через исключение.

Ключевая структура данных — `_OuterCallCollector`, наследник `ast.NodeVisitor`. Этот класс обходит AST и собирает только вызовы из тела функции, но намеренно не спускается в тела вложенных функций. Почему? Потому что вложенные функции не выполняются в момент вызова внешней функции, если их не вызвать явно. Мы записываем их отдельно и анализируем только тогда, когда они действительно вызываются.

```python
class _OuterCallCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[CallLocation] = []
        self.local_functions: dict[str, FunctionDefLike] = {}

    def visit_Call(self, node: ast.Call) -> None:
        target, is_dynamic = _format_target(node.func)
        short_name = target.rsplit(".", maxsplit=1)[-1]

        self.calls.append(
            CallLocation(
                target=target,
                short_name=short_name,
                lineno=node.lineno,
                col_offset=node.col_offset,
                is_dynamic=is_dynamic,
            )
        )

        if isinstance(node.func, ast.Lambda):
            self.visit(node.func.body)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: FunctionDefLike) -> None:
        self.local_functions[node.name] = node
        self._visit_function_definition_creation(node)
```

В `visit_Call` мы форматируем целевой вызов через `_format_target` и сохраняем его в список `calls`. Особый случай — сразу вызванные лямбды вида `(lambda: foo())()`. Здесь `node.func` — это `ast.Lambda`, и мы должны проанализировать его тело, потому что оно выполняется немедленно. Для таких случаев мы явно вызываем `self.visit(node.func.body)`.

В `visit_FunctionDef` мы запоминаем определение вложенной функции в `local_functions`, но не спускаемся в её тело. Это позволяет нам отложить анализ до момента, когда мы узнаем, что эта функция действительно вызывается. Асинхронные функции обрабатываются точно так же через `visit_AsyncFunctionDef = visit_FunctionDef`.

Класс `visit_ClassDef` обрабатывает определение класса. Тело класса выполняется во время определения, поэтому мы анализируем декораторы, базовые классы, аргументы ключевых слов и выражения на уровне класса. Но методы класса мы не анализируем — они будут вызваны только при создании экземпляра и вызове метода, поэтому их анализ откладывается.

`_visit_function_definition_creation` обрабатывает декораторы и аргументы по умолчанию, потому что они вычисляются в момент определения функции и могут содержать вызовы. Это важный нюанс — декоратор `@log(calculate())` выполнит `calculate()` во время декорирования, еще до вызова самой функции.

`_format_target` — это вспомогательная функция, которая преобразует AST-выражение вызова в текстовое представление и определяет, является ли вызов динамическим.

```python
def _format_target(node: ast.expr) -> tuple[str, bool]:
    if isinstance(node, ast.Name):
        return node.id, False

    if isinstance(node, ast.Attribute):
        base, dynamic = _format_target(node.value)
        if dynamic:
            return f"<dynamic>.{node.attr}", True
        return f"{base}.{node.attr}", False

    if isinstance(node, ast.Call):
        return "<call-result>", True

    if isinstance(node, ast.Subscript):
        return "<subscript>", True

    return "<dynamic>", True
```

Если вызов — это просто имя (`os`), мы возвращаем его. Если это атрибут (`os.system`), мы рекурсивно форматируем базовое выражение и добавляем атрибут. Если базовое выражение динамическое (`getattr(os, 'system')()`), то весь вызов помечается как динамический. Для вызовов вида `foo()()`, индексов `list[0]()` и любых других непонятных конструкций мы помечаем их как динамические и возвращаем заглушки.

Это важно для безопасности — динамические вызовы не могут быть надежно разрешены статически, поэтому мы помечаем их как потенциально опасные.

`SafeResolver` — еще один ключевой компонент. Он отвечает за безопасное разрешение имен в объекты. Обычный `getattr` может запустить дескрипторы и выполнить произвольный код, что недопустимо при статическом анализе.

```python
class SafeResolver:
    def resolve(
        self,
        name: str,
        parent_func: Callable[..., Any] | None,
    ) -> Callable[..., Any] | None:
        if parent_func is None:
            return None

        if not name or name.startswith("<"):
            return None

        parts = name.split(".")

        try:
            parent_globals = parent_func.__globals__
        except AttributeError:
            return None

        obj = parent_globals.get(parts[0])

        if obj is None:
            obj = getattr(builtins, parts[0], None)

        if obj is None:
            return None

        for part in parts[1:]:
            if not isinstance(obj, (types.ModuleType, type)):
                return None

            obj = inspect.getattr_static(obj, part, None)

            if obj is None:
                return None

        return obj if callable(obj) else None
```

`SafeResolver` берет имя (`"os.system"`) и родительскую функцию, в контексте которой это имя используется. Из `__globals__` родительской функции мы получаем объект для первого сегмента имени (`os`), затем проходим по оставшимся сегментам, проверяя, что каждый промежуточный объект — это модуль или класс. Мы используем `inspect.getattr_static`, чтобы не запускать дескрипторы и свойства. И в конце проверяем, что полученный объект вызываемый.

Такой подход исключает выполнение произвольного кода во время разрешения, что критично для безопасности.

`CallNode` — это узел графа вызовов. Он хранит идентификатор функции (`identity`), имя вызова (`call_name`), позицию в исходном коде (`lineno`, `col_offset`), разрешенный объект (`resolved_func`), если он известен, и флаги состояния.

```python
@dataclass
class CallNode:
    identity: str
    call_name: str
    lineno: int | None = None
    col_offset: int | None = None
    resolved_func: Callable[..., Any] | None = None
    is_local_definition: bool = False
    is_dynamic: bool = False
    is_unresolved: bool = False
    is_source_available: bool = True
    is_cycle: bool = False
    children: list[CallNode] = field(default_factory=list)
```

`is_local_definition` указывает, что узел — это локальная функция, определенная внутри родительской. `is_unresolved` — мы не смогли разрешить вызов. `is_dynamic` — вызов динамический. `is_cycle` — обнаружена рекурсия, чтобы не уйти в бесконечный обход. `children` — дочерние узлы, представляющие вызовы внутри этой функции.

`CallTree` — это основной класс для построения графа вызовов.

```python
class CallTree:
    def __init__(
        self,
        func: Callable[..., Any],
        max_depth: int | float = 1,
        resolver: SafeResolver | None = None,
    ) -> None:
        self.max_depth: int | float = max(0, max_depth)
        self.resolver = resolver or SafeResolver()
        self.root = self._build_from_callable(
            func=func,
            depth=0,
            stack=frozenset(),
            require_source=True,
        )
```

При создании `CallTree` мы начинаем с корневой функции. `max_depth` контролирует глубину рекурсивного обхода — это позволяет ограничить анализ для производительности или при `recursive=False`. `_build_from_callable` строит узел для корневой функции и рекурсивно обходит все вызовы.

Процесс построения выглядит так: сначала мы создаем узел для текущей функции. Если эта функция уже есть в стеке вызовов (`identity in stack`) — мы помечаем узел как цикл и останавливаемся, чтобы избежать бесконечной рекурсии. Если достигнута максимальная глубина — останавливаемся. Затем пытаемся получить AST функции через `_get_function_ast`. Если это не удается и `require_source=True`, мы пробрасываем исключение. В противном случае помечаем узел как недоступный источник.

`_expand_node` — ключевой метод, который раскрывает тело функции. Он извлекает вызовы и локальные определения через `extract_calls_from_function_def`, затем для каждого вызова строит дочерний узел через `_build_child`.

`_build_child` решает, как обработать конкретный вызов. Если это не динамический вызов и имя не содержит точек, мы пытаемся найти локальное определение в `local_defs`. Если находим — строим узел из AST через `_build_from_ast`. Если нет — пытаемся разрешить через `SafeResolver`. Если разрешение успешно — строим узел из разрешенного callable-объекта через `_build_from_callable`. Если нет — создаем узел с пометкой `is_unresolved`.

Такой подход позволяет строить граф вызовов максимально полно, но при этом безопасно — мы не выполняем код, не запускаем дескрипторы, не ходим по ссылкам в рантайме.

## namespace.py

`IntentNamespace` — это движок политик. Он принимает правила и применяет их к графу вызовов.

```python
class IntentNamespace:
    def __init__(
        self,
        uses: Iterable[Rule] | None = None,
        *,
        recursive: bool = True,
        without: Iterable[Rule] | None = None,
        uselocals: bool = False,
        usemodule: bool = False,
        deny: Iterable[Rule] | None = None,
        allow_unknown: bool = False,
        deny_dynamic_primitives: bool = True,
        only_warnings: bool = False,
    ) -> None:
```

`uses` — белый список разрешенных вызовов. `without` — список функций, которые исключаются из проверки белого списка. `deny` — черный список запрещенных вызовов. `uselocals` — разрешает локальные определения. `usemodule` — разрешает функции из того же модуля. `allow_unknown` — разрешает неразрешенные вызовы. `deny_dynamic_primitives` — блокирует динамические примитивы по умолчанию. `only_warnings` — вместо исключений выводит предупреждения.

Правила нормализуются в `RuleSet` через `_normalize_rules`. Это позволяет задавать правила как строки (`"os.system"`), так и callable-объекты (`os.system`).

```python
@dataclass(frozen=True)
class RuleSet:
    objects: frozenset[Callable[..., Any]] = frozenset()
    identities: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()
    short_names: frozenset[str] = frozenset()
```

`RuleSet` хранит правила в четырех формах: объекты, идентификаторы (`module:qualname`), полные имена (`module.qualname`) и короткие имена. Это позволяет гибко проверять совпадения.

`_normalize_rules` обрабатывает строки с двоеточием как идентификаторы, строки с точкой как полные имена, а простые строки как короткие имена.

Метод `matches` в `RuleSet` проверяет, соответствует ли узел правилу. Он проверяет в порядке: объект, идентификатор, полное имя, короткое имя.

```python
def matches(self, node: CallNode) -> bool:
    if node.resolved_func is not None:
        try:
            if node.resolved_func in self.objects:
                return True
        except TypeError:
            pass

        if get_function_identity(node.resolved_func) in self.identities:
            return True

    if node.identity in self.identities:
        return True

    if node.call_name in self.names:
        return True

    short_name = node.call_name.rsplit(".", maxsplit=1)[-1]
    return short_name in self.short_names
```

При проверке мы сначала пробуем объектную проверку, но если объект нехешируемый, ловим `TypeError` и продолжаем. Затем проверяем идентификатор, полное имя и короткое имя.

Главный метод `intent` возвращает декоратор, который оборачивает функцию.

```python
def intent(...) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    # формируем эффективную политику
    policy = _EffectivePolicy(...)
    max_depth = float("inf") if effective_recursive else 1

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tree = CallTree(func, max_depth=max_depth)
            root_module = getattr(func, "__module__", None)
            self._validate_tree(tree.root, policy, root_module=root_module)
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

Декоратор при каждом вызове строит `CallTree` и проверяет его через `_validate_tree`. Если проверка не пройдена, функция не выполняется.

`_validate_tree` обходит граф вызовов в глубину. Для каждого узла, кроме корневого, проверяется: если узел есть в `deny` — нарушение. Затем проверяется `without`: если узел не в `without` и не разрешен через `_is_allowed` — нарушение.

`_is_allowed` определяет, разрешен ли узел. Проверяются: `uses`, `uselocals` для локальных определений, `usemodule` для функций из того же модуля и `allow_unknown` для неразрешенных или динамических вызовов.

Порядок важен: `deny` проверяется первым, поэтому он всегда имеет приоритет над `uses` и `without`. Это позволяет явно запретить опасные функции, даже если они указаны в `uses`.

`usemodule` требует `recursive=True`, потому что проверка функций из того же модуля имеет смысл только при рекурсивном обходе графа.

## exceptions.py

Исключения выстроены в иерархию: `IntentError` — базовый класс. `IntentViolationError` — нарушение политики. `IntentParseError` — ошибка парсинга кода. `IntentConfigurationError` — ошибка конфигурации.

`IntentViolationError` хранит имя функции, нарушение и путь вызовов для детального сообщения об ошибке.

```python
class IntentViolationError(IntentError):
    def __init__(
        self,
        func_name: str,
        violation: str,
        *,
        path: tuple[str, ...] = (),
    ) -> None:
        self.func_name = func_name
        self.violation = violation
        self.path = tuple(path)

        if self.path:
            where = " -> ".join((*self.path, func_name))
        else:
            where = func_name

        super().__init__(f"Function '{where}' calls forbidden '{violation}'")
```

Это дает нам красивые сообщения: `Function 'func -> outer -> inner' calls forbidden 'os.system'`, как в примере.

AST-интроспекция строит граф вызовов, политики проверяют каждый узел, а если что-то не так — исключение выбрасывается до выполнения функции. В следующей части я покажу, как этим пользоваться на практике, и разберу ограничения, с которыми столкнулся из-за динамичной природы Python.

# Примеры использования

Теперь, когда мы разобрались с архитектурой, давайте посмотрим на библиотеку в действии. Начнем с простого примера, который я показывал в начале статьи.

```python
import os

from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(
    uses=[print],
    recursive=True,
)


@namespace.intent()
def safe_function() -> None:
    print("This is allowed")


@namespace.intent()
def unsafe_function() -> None:
    os.system("echo This should be blocked")


if __name__ == "__main__":
    safe_function()

    try:
        unsafe_function()
    except IntentViolationError as exc:
        print(f"Blocked: {exc}")
```

Мы создаем неймспейс с единственным разрешением — функция `print`. Безопасная функция `safe_function` выполняется нормально, потому что она вызывает только `print`. А вот `unsafe_function` при попытке вызова выбрасывает `IntentViolationError`, потому что `os.system` не указан в `uses`. Самое важное здесь — `unsafe_function` вообще не выполняется, ошибка возникает до того, как код начнет работать.

Теперь усложним пример. Добавим вложенные функции и включим `usemodule`.

```python
import os

from pyintents import IntentNamespace

main_namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    usemodule=True,
)


def inner() -> None:
    os.system("rm test.txt")


def outer() -> None:
    print("Outer")
    inner()


@main_namespace.intent()
def func() -> None:
    print("Func")
    outer()


if __name__ == "__main__":
    try:
        func()
    except Exception as exc:
        print(f"Error: {exc}")
```

Здесь `recursive=True` включает рекурсивную проверку — PyIntents анализирует не только тело `func`, но и все функции, которые она вызывает. `usemodule=True` означает, что функции, определенные в том же модуле, что и декорированная функция, разрешены автоматически. Это удобно, когда у вас много вспомогательных функций, и вы не хотите перечислять их все в `uses`.

При вызове `func` происходит следующее: PyIntents строит граф вызовов `func -> outer -> inner`. На каждом узле проверяется, разрешен ли вызов. `print` разрешен явно через `uses`. `outer` и `inner` разрешены через `usemodule` — они определены в том же модуле. А вот `os.system` внутри `inner` не разрешен, и мы получаем ошибку с полным путем: `Function 'func -> outer -> inner' calls forbidden 'os.system'`.

`usemodule` работает только в связке с `recursive=True`. Если вы попытаетесь включить `usemodule` без рекурсии, получите `IntentConfigurationError`. Это логично — разрешать функции из того же модуля имеет смысл только если мы проверяем их содержимое.

Теперь рассмотрим сценарий с локальными вложенными функциями.

```python
from pyintents import IntentNamespace, IntentViolationError

namespace = IntentNamespace(
    uses=[print],
    recursive=True,
    uselocals=True,
)


@namespace.intent()
def ok_function() -> None:
    def local_helper() -> None:
        print("Local helper is allowed")

    local_helper()


@namespace.intent()
def bad_function() -> None:
    def local_helper() -> None:
        import os

        os.system("echo This should be blocked")

    local_helper()


if __name__ == "__main__":
    ok_function()

    try:
        bad_function()
    except IntentViolationError as exc:
        print(f"Blocked: {exc}")
```

Здесь мы включаем `uselocals=True`, что разрешает вызовы локальных функций, определенных внутри декорируемой функции. `ok_function` определяет `local_helper`, которая вызывает `print` — все разрешено, функция выполняется. А вот `bad_function` определяет `local_helper`, которая внутри себя импортирует `os` и вызывает `os.system`. PyIntents находит этот вызов в графе, видит, что `os.system` не разрешен, и блокирует выполнение всей цепочки.

Важный момент: `uselocals` разрешает саму локальную функцию как вызов, но не отключает проверку того, что эта локальная функция вызывает внутри себя. То есть `local_helper` разрешена как вызов, но ее содержимое все равно проверяется.

Теперь о ситуации, когда нам нужно отладить политику или мигрировать существующий код. PyIntents предоставляет режим `only_warnings`, который вместо исключений выводит предупреждения. Это позволяет увидеть все нарушения, не блокируя выполнение.

```python
from pyintents import IntentNamespace
import warnings

warnings.simplefilter("always")  # чтобы увидеть предупреждения

namespace = IntentNamespace(
    uses=[print],
    only_warnings=True,
)


def helper():
    import os
    os.system("echo This would be blocked")


@namespace.intent()
def func():
    print("Hello")
    helper()


if __name__ == "__main__":
    func()  # Выполнится, но выведет предупреждение о нарушении
```

В этом режиме функция выполнится, но в консоль будет выведено предупреждение: `UserWarning: Intent violation: os.system called from func.helper`. Это полезно при внедрении PyIntents в существующий проект — вы можете включить `only_warnings`, увидеть все потенциальные нарушения, исправить их, и только потом переключиться на строгий режим с исключениями.

`deny` позволяет явно запретить определенные вызовы, даже если они есть в `uses`. Это может быть полезно, когда вы хотите разрешить целую группу функций, но запретить конкретную опасную.

```python
import os

namespace = IntentNamespace(
    uses=[print, os.system],
    deny=[os.system],
)


@namespace.intent()
def restricted():
    print("OK")
    os.system("echo This is explicitly denied")
```

Здесь `os.system` одновременно и разрешен через `uses`, и запрещен через `deny`. Приоритет у `deny` выше, поэтому вызов будет заблокирован.

И наконец, `allow_unknown` — параметр, который разрешает неразрешенные вызовы. По умолчанию он выключен, что соответствует модели fail-closed. Но в некоторых случаях, например при работе с динамическими вызовами, которые невозможно разрешить статически, его можно включить.

```python
namespace = IntentNamespace(
    uses=[print],
    allow_unknown=True,
)


@namespace.intent()
def dynamic_call():
    cb = print
    cb("This works with allow_unknown=True")
```

В этом примере `cb()` не может быть разрешен статически, потому что `cb` — локальная переменная. С `allow_unknown=False` такой вызов был бы заблокирован. С `allow_unknown=True` — разрешен. Используйте это с осторожностью, потому что `allow_unknown` ослабляет проверки.

# Под капотом: нетривиальные случаи и ограничения

К сожалению, я хоть и покрыл почти все способы вызова функции, но все равно столкнулся с несколькими сложными моментами, которые хорошо иллюстрируют, где статический анализ упирается в динамическую природу Python. Начну с того, как я обрабатывал разные виды вызовов.

Самый простой случай — прямой вызов по имени: `os.system("ls")`. AST представляет его как `ast.Attribute`, где `value` — это `ast.Name("os")`, а `attr` — `"system"`. `_format_target` преобразует это в строку `"os.system"`, и `SafeResolver` находит соответствующий объект через `__globals__` родительской функции.

Но что, если вызов динамический? Например, `getattr(os, "system")("ls")`. Здесь `getattr` возвращает функцию по строковому имени. Статически мы не можем определить, какую именно функцию вернет `getattr` — это зависит от рантайма. `_format_target` видит `ast.Call` в качестве базового выражения и помечает весь вызов как динамический: `"<dynamic>.system"`. Такой вызов не может быть разрешен через `SafeResolver`, и он либо блокируется, либо пропускается в зависимости от `allow_unknown`.

Локальные переменные-колбэки — еще один интересный случай. В коде `cb = print; cb("hello")` вызов `cb()` не содержит точек, это просто `ast.Name("cb")`. `SafeResolver` не может разрешить `cb`, потому что это локальная переменная, ее нет в `__globals__`. Такой вызов помечается как `is_unresolved` и, по умолчанию, блокируется. Это правильное поведение — если мы не можем статически определить, что такое `cb`, мы не можем гарантировать безопасность.

Отдельного внимания заслуживают сразу вызванные лямбды: `(lambda: os.system("ls"))()`. В AST это `ast.Call`, где `func` — это `ast.Lambda`. В обычной ситуации мы не спускаемся в тело лямбды, потому что она будет выполнена только при вызове. Но здесь она вызывается немедленно. В `visit_Call` я добавил проверку: если `node.func` — это `ast.Lambda`, мы явно вызываем `self.visit(node.func.body)`, анализируя тело лямбды как часть текущего контекста выполнения. Это позволяет обнаружить `os.system` внутри немедленно вызванной лямбды.

С классами ситуация сложнее. Тело класса выполняется во время определения, поэтому я анализирую декораторы классов, базовые классы, аргументы ключевых слов и выражения на уровне класса. Например, декоратор `@log(calculate())` вызовет `calculate()` во время декорирования, еще до создания экземпляра класса. А вот методы класса я не анализирую — они будут вызваны только при создании экземпляра и вызове метода. Их анализ откладывается до момента, когда мы увидим вызов `instance.method()` в графе.

Рекурсия — еще одна проблема. Если функция вызывает саму себя, граф вызовов становится бесконечным. Чтобы этого избежать, я передаю стек уже обработанных идентификаторов в `_build_from_callable` и `_build_from_ast`. Если мы встречаем функцию, чей идентификатор уже есть в стеке, мы помечаем узел как `is_cycle` и не раскрываем его дальше. Это позволяет корректно обрабатывать рекурсивные функции, не уходя в бесконечный обход.

Теперь об ограничениях. PyIntents — это слой безопасности, но не полноценная песочница. Полная защита от динамического Python невозможна в принципе. Рассмотрим такой код:

```python
eval("import os; os.system('rm -rf /')")
```

`eval` входит в список `DEFAULT_DENIED_DYNAMIC_PRIMITIVES` и блокируется по умолчанию. Но если разработчик явно разрешит `eval` через `uses`, PyIntents не сможет проанализировать строку, переданную в `eval` — это произвольный код, который может содержать что угодно.

Другой пример:

```python
globals()["os"].system("ls")
```

`globals()` также входит в список запрещенных примитивов. Но если разрешить `globals()` и `getattr()`, можно обойти практически любую проверку. Именно поэтому я запрещаю эти примитивы по умолчанию.

Важно понимать: PyIntents работает на уровне AST, анализируя статическую структуру кода. Он не может анализировать строки, передаваемые в `eval`, или значения переменных в рантайме. Это фундаментальное ограничение любого статического анализа.

Что можно сделать для улучшения? На данный момент `CallTree` строится при каждом вызове декорированной функции. Это не проблема для функций, которые вызываются редко, но для высоконагруженных hot-path функций это создает задержку. Планируется добавить кеширование: построенное дерево для каждой декорированной функции будет сохраняться после первого вызова и переиспользоваться при следующих вызовах. Это значительно повысит производительность, потому что AST-анализ будет выполняться только один раз.

Также в планах — улучшить обработку декораторов. Сейчас декораторы с параметрами анализируются корректно, но если декоратор возвращает другой объект (например, `@staticmethod` или `@classmethod`), анализ может давать ложные срабатывания. Это требует более глубокого понимания того, как декораторы трансформируют функции.

Еще одно направление — поддержка анализа импортов. Сейчас PyIntents видит только вызовы внутри анализируемой функции. Если функция вызывает функцию из другого модуля, которая импортирует `os` внутри себя, этот импорт будет обнаружен при анализе этой функции. Но если модуль импортирует что-то на уровне модуля, а функция использует это как глобальную переменную, это работает только через `SafeResolver` и `__globals__`.

Но главное ограничение остается: Python слишком динамичен для полной статической гарантии безопасности. PyIntents — это инструмент, который делает код более безопасным и предсказуемым, но он не заменяет другие уровни защиты: изоляцию процессов, контейнеры, seccomp, WASM. Используйте его как часть многоуровневой стратегии безопасности или как поле для экспериментов.

# Заключение

Capability-based Security — это мощная концепция, которая десятилетиями доказывала свою эффективность на уровне операционных систем и аппаратного обеспечения. PyIntents — моя попытка привнести эту идею в экосистему Python, адаптировав её под динамическую природу языка через статический анализ и декларативные интенты.

Мне удалось реализовать рабочую систему, которая позволяет разработчикам явно декларировать намерения своих функций и проверять их до выполнения. Это не серебряная пуля, но полезный инструмент для случаев, где контроль над тем, что может делать функция, критичен.

Как я уже говорил, библиотека доступна на PyPI: `pip install pyintents`. Исходный код открыт и лежит на [GitHub](https://github.com/alexeev-prog/pyintents/). Там же можно найти документацию, примеры и инструкции по установке.

PyIntents, по моему скромнейшему мнению, особенно полезен в системах плагинов, где вы не доверяете стороннему коду, в AI-агентах, где нужно ограничить набор доступных инструментов, и в тестировании, где важно изолировать зависимости. Это хоть и не замена полноценной песочнице, но зато отличный слой безопасности для Python-приложений.

Я буду рад, если вы попробуете PyIntents в своих проектах. Если найдете баги, придумаете интересные сценарии использования или захотите улучшить что-то в коде — открывайте issues, предлагайте pull request'ы. Особенно актуальны идеи по оптимизации производительности и обработке сложных декораторов.

Явное лучше, чем неявное, как говорится!
