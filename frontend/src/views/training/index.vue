<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>安全培训管理</h2>
        <p class="page-desc">主题看板与明细清单读取同一份培训数据，点击主题只看相关记录；复训到期人数单独提示。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记培训记录</button>
        <button class="btn" type="button" @click="exportRows">导出安全培训清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="topic-board">
      <article
        v-for="topic in boardTopics"
        :key="topic.topic"
        class="topic-card"
        :class="{ active: selectedTopic === topic.topic, unscheduled: !topic.scheduled }"
        role="button"
        tabindex="0"
        @click="selectTopic(topic.topic)"
        @keydown.enter="selectTopic(topic.topic)"
      >
        <header class="topic-head">
          <h3 class="topic-name">{{ topic.topic }}</h3>
          <span v-if="!topic.scheduled" class="topic-badge muted">待安排</span>
          <span v-else-if="topic.retrain_due" class="topic-badge warn">复训到期</span>
        </header>
        <template v-if="topic.scheduled">
          <dl class="topic-metrics">
            <div class="topic-metric">
              <dt>培训日期</dt>
              <dd>{{ topic.latest_date ?? '—' }}</dd>
            </div>
            <div class="topic-metric">
              <dt>培训讲师</dt>
              <dd>{{ topic.latest_instructor ?? '—' }}</dd>
            </div>
            <div class="topic-metric">
              <dt>参训人数</dt>
              <dd>{{ topic.total_trainees }}</dd>
            </div>
            <div class="topic-metric">
              <dt>考核通过</dt>
              <dd>{{ topic.total_passed }}</dd>
            </div>
          </dl>
          <div class="topic-progress">
            <div class="topic-progress-bar">
              <span class="topic-progress-fill" :style="{ width: percent(topic.pass_rate) }"></span>
            </div>
            <span class="topic-progress-text">完成比例 {{ percent(topic.pass_rate) }}</span>
          </div>
          <p v-if="topic.retrain_due" class="topic-note warn-text">
            复训到期 {{ topic.retrain_due_count }} 人，已超期 {{ topic.overdue_days }} 天
          </p>
        </template>
        <p v-else class="topic-note">该主题暂无培训记录，待安排</p>
      </article>
    </div>

    <div class="board-summary">
      <span v-if="selectedTopic">
        当前只看「{{ selectedTopic }}」相关记录
        <button class="link" type="button" @click="clearTopic">查看全部主题</button>
      </span>
      <span v-else>点击上方主题卡片，只看该主题相关记录</span>
      <span class="warn-text">复训到期人数：{{ retrainDueCount }} 人</span>
    </div>

    <form class="filter-bar" @submit.prevent>
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="keyword" placeholder="按编号、讲师、资料检索" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filteredRows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!filteredRows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyMessage }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>
        共 {{ filteredRows.length }} 条安全培训记录
        <template v-if="filteredRows.length !== total">（全部 {{ total }} 条）</template>
      </span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

type TopicBoard = {
  topic: string
  scheduled: boolean
  record_count: number
  latest_date: string | null
  latest_instructor: string | null
  total_trainees: number
  total_passed: number
  pass_rate: number | null
  retrain_due: boolean
  retrain_due_count: number
  overdue_days: number
  records: Row[]
}

type BoardPayload = {
  as_of: string
  retrain_cycle_days: number
  topics: TopicBoard[]
  total_sessions: number
  retrain_due_count: number
}

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
const actions = ["组织培训", "登记考核", "安排补训"]
const statuses = ["计划中", "已组织", "已完成", "需补训"]

const boardTopics = ref<TopicBoard[]>([])
const rows = ref<Row[]>([])
const total = ref(0)
const retrainDueCount = ref(0)
const asOf = ref('')
const selectedTopic = ref('')
const keyword = ref('')
const statusFilter = ref('')
const errorMessage = ref('')

function toInt(value: unknown): number {
  const num = Number(value)
  return Number.isFinite(num) ? Math.trunc(num) : 0
}

function percent(rate: number | null): string {
  return rate === null ? '—' : `${Math.round(rate * 100)}%`
}

const filteredRows = computed(() => {
  const kw = keyword.value.trim()
  return rows.value.filter((row) => {
    if (selectedTopic.value && String(row['培训主题'] ?? '') !== selectedTopic.value) return false
    if (statusFilter.value && String(row['培训状态'] ?? '') !== statusFilter.value) return false
    if (kw) {
      const haystack = [row['培训编号'], row['培训主题'], row['培训讲师'], row['培训资料']]
        .map((value) => String(value ?? ''))
        .join(' ')
      if (!haystack.includes(kw)) return false
    }
    return true
  })
})

const stats = computed(() => {
  const month = asOf.value.slice(0, 7)
  const monthCount = rows.value.filter((row) => String(row['培训日期'] ?? '').startsWith(month)).length
  // 通过率只统计已出考核结果的场次，计划中的培训不拖低比例。
  const assessed = rows.value.filter((row) => row['考核通过'] !== null && row['考核通过'] !== undefined && row['考核通过'] !== '')
  const trainees = assessed.reduce((sum, row) => sum + toInt(row['参训人数']), 0)
  const passed = assessed.reduce((sum, row) => sum + toInt(row['考核通过']), 0)
  return [
    { label: '本月培训', value: monthCount },
    { label: '通过率', value: trainees ? `${Math.round((passed / trainees) * 100)}%` : '—' },
    { label: '复训到期人数', value: retrainDueCount.value },
  ]
})

const emptyMessage = computed(() => {
  if (selectedTopic.value && !rows.value.some((row) => row['培训主题'] === selectedTopic.value)) {
    return `主题「${selectedTopic.value}」暂无培训记录，待安排`
  }
  if (selectedTopic.value || keyword.value || statusFilter.value) {
    return '没有符合筛选条件的培训记录'
  }
  return '暂无安全培训数据，可先登记培训记录'
})

function selectTopic(topic: string) {
  selectedTopic.value = selectedTopic.value === topic ? '' : topic
}

function clearTopic() {
  selectedTopic.value = ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  selectedTopic.value = ''
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '培训记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('安全培训动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (!response.ok) {
      throw new Error('培训看板读取失败')
    }
    const payload = (await response.json()) as BoardPayload
    boardTopics.value = payload.topics ?? []
    // 看板与明细共用这一次返回的数据，明细不再单独请求列表接口。
    rows.value = boardTopics.value.flatMap((topic) => topic.records)
    total.value = payload.total_sessions ?? rows.value.length
    retrainDueCount.value = payload.retrain_due_count ?? 0
    asOf.value = payload.as_of ?? ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训数据读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.topic-board {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}
.topic-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.topic-card:hover {
  border-color: var(--brand);
}
.topic-card.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.15);
}
.topic-card.unscheduled {
  background: #fafbfc;
  border-style: dashed;
}
.topic-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.topic-name {
  margin: 0;
  font-size: 14px;
}
.topic-badge {
  font-size: 12px;
  border-radius: 10px;
  padding: 1px 8px;
}
.topic-badge.muted {
  color: var(--muted);
  border: 1px dashed var(--border);
}
.topic-badge.warn {
  color: #b42318;
  border: 1px solid #f3c2bd;
  background: #fef3f2;
}
.topic-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 10px;
  margin: 0 0 8px;
}
.topic-metric dt {
  font-size: 12px;
  color: var(--muted);
}
.topic-metric dd {
  margin: 0;
  font-size: 13px;
}
.topic-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}
.topic-progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #eef2f7;
  overflow: hidden;
}
.topic-progress-fill {
  display: block;
  height: 100%;
  background: var(--brand);
}
.topic-progress-text {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}
.topic-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.warn-text {
  color: #b42318;
}
.board-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--muted);
}
.board-summary .link {
  margin-left: 8px;
}
</style>
