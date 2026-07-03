# 键位映射 JSON
[
  {"logical": "<名字>", "physical": "<键名>", "group": "<分组>", "cooldown_ms": <冷却>, "jitter_ms": <抖动>, "after_min_ms": <min>, "after_max_ms": <max>, "weight": <权重>},
  ...
]

# 字段说明
# - logical: 任意字符串，仅用于显示
# - physical: 键名（小写），见下表
# - group: "execute" / "move" / "buff"（不填默认 execute）
#   - execute: 执行区（每轮随机出现多次，按权重抽，受 cd 限制）
#   - move:    移动区（每轮只出现 1 次）
#   - buff:    BUFF 区（每轮只出现 1 次）
# - cooldown_ms: 基础冷却（毫秒）
# - jitter_ms: 0~+N 抖动（只延后不提前），0=无抖动
# - after_min_ms / after_max_ms: 发完后到选下一个键的等待区间
# - weight: 加权，0=禁用

# 键名表（按 SCANCODE 字典）
# 字母: a b c d e f g h i j k l m n o p q r s t u v w x y z
# 数字: 0 1 2 3 4 5 6 7 8 9
# 符号: ` - = [ ] \ ; ' , . /
# 修饰: shift ctrl alt caps num scroll
# 基础: space enter escape tab back
# 方向: up down left right home end insert delete pageup pagedown
# 功能键: f1 f2 f3 f4 f5 f6 f7 f8 f9 f10 f11 f12
# 小键盘: numpad0~numpad9 multiply add subtract decimal divide
