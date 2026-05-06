## 🧠 {{ event_name }}

> 决策状态：**{{ decision_signal }}** · 生命周期：**{{ status }}** · 重要度：{{ importance }} · 记忆强度：{{ strength }}

### 会话范围
`{{ project }}`

### 📌 事件概览
{{ summary }}

### ✅ 决策结果
{{ decision_result }}

### 🗂️ 关键信息
- **别名**：{{ aliases }}
- **相关实体**：{{ entities }}
- **截止 / 时间约束**：{{ deadline }}
{% if participants_lines %}
- **参与者**：
{% for p in participants_lines %}  - {{ p }}
{% endfor %}
{% endif %}

{% if reasons_lines %}
### 支持理由
{% for r in reasons_lines %}- {{ r }}
{% endfor %}
{% endif %}

{% if objections_lines %}
### 反对与风险
{% for o in objections_lines %}- {{ o }}
{% endfor %}
{% endif %}

{% if alternatives_lines %}
### 备选 / 被否方案
{% for a in alternatives_lines %}- {{ a }}
{% endfor %}
{% endif %}
