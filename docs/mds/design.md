# 记忆模块设计

您可以在[hiarch_memory/memory.py](../../nanobot/nanobot/agent/hiarch_memory/memory.py)文件中找到关于长期记忆架构的定义。同一目录下可以找到其他不同类型记忆的实现，由于时间原因，只实现了短期记忆（[shorterm.py](../../nanobot/nanobot/agent/hiarch_memory/shorterm.py)）以及情景记忆（[episodic.py](../../nanobot/nanobot/agent/hiarch_memory/episodic.py)），后续设想情景记忆、语义记忆等长期记忆统一通过`memory.py`中的`aggregation_memory`方法管理与nanobot的处理流对接：
```python
async def aggregation_memory(self, current_message: str) -> str:
    # Add Router
    mem: str = ''
    # First: Retrieve Knowledge
    kwg: str = await self._episodic_memorystore.retrieve(current_message)
    print(kwg)
    if kwg: mem += kwg
    return mem
```
在nanobot的[context.py](../../nanobot/nanobot/agent/context.py)的`_build_system_prompt`方法中体现了这一点：
```python
...
bootstrap = self._load_bootstrap_files()
if bootstrap:
    parts.append(bootstrap)

memory = await self.memory.aggregation_memory(current_message)
if memory and self.memory.efficient():
    parts.append(f"# Memory\n\n{memory}")

always_skills = self.skills.get_always_skills()
if always_skills:
...
```

Continue to update...