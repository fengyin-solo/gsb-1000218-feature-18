<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>安全培训管理</h2>
        <p class="page-desc">按培训主题排布看板，统一展示培训日期、讲师、参训与考核通过情况；点击主题可只看相关培训记录。</p>
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

    <section class="board" aria-label="按主题排布的安全培训看板">
      <button
        v-for="topic in topics"
        :key="topic.topic"
        type="button"
        class="board-col"
        :class="{ active: filters.topic === topic.topic, empty: !topic.arranged }"
        @click="selectTopic(topic.topic)"
      >
        <header class="board-col-head">
          <span class="board-topic">{{ topic.topic }}</span>
          <span class="board-badge" :class="topic.arranged ? 'ok' : 'todo'">
            {{ topic.arranged ? `${topic.record_count} 场` : '待安排' }}
          </span>
        </header>

        <template v-if="topic.arranged">
          <dl class="board-meta">
            <div><dt>最近培训</dt><dd>{{ topic.latest_date ?? '—' }}</dd></div>
            <div><dt>讲师</dt><dd>{{ topic.latest_trainer ?? '—' }}</dd></div>
            <div><dt>参训人数</dt><dd>{{ topic.attend_total }} 人</dd></div>
            <div><dt>考核通过</dt><dd>{{ topic.pass_total }} 人</dd></div>
          </dl>
          <div class="board-rate">
            <div class="rate-line">
              <span>完成比例</span>
              <strong>{{ formatPercent(topic.completion_rate) }}</strong>
            </div>
            <div class="rate-bar"><i :style="{ width: formatPercent(topic.completion_rate) }"></i></div>
          </div>
          <p v-if="topic.retrain_due > 0" class="board-due">复训到期 {{ topic.retrain_due }} 人，请尽快安排复训</p>
          <p v-else class="board-fresh">复训有效期内</p>
        </template>
        <p v-else class="board-empty-note">该主题暂无培训记录，筛选已保留，待安排后在此呈现汇总。</p>
      </button>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>培训编号</span>
        <input v-model="filters.keyword" placeholder="按培训编号检索" />
      </label>
      <label class="filter-item">
        <span>培训讲师</span>
        <input v-model="filters.trainer" placeholder="按培训讲师检索" />
      </label>
      <label class="filter-item">
        <span>培训状态</span>
        <input v-model="filters.status" placeholder="计划中/已组织/已完成/需补训" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span v-if="filters.topic" class="topic-chip">
        看板主题：{{ filters.topic }}
        <button class="link" type="button" @click="clearTopic">清除主题筛选</button>
      </span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
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
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">
            <template v-if="filters.topic">「{{ filters.topic }}」主题下暂无培训记录，主题筛选已保留，可登记该主题的培训安排</template>
            <template v-else>暂无安全培训数据，可先登记培训记录</template>
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条安全培训记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface BoardTopic {
  topic: string
  arranged: boolean
  record_count: number
  latest_date: string | null
  latest_trainer: string | null
  attend_total: number
  pass_total: number
  completion_rate: number
  retrain_due: number
  items: Row[]
}

interface ListPayload {
  items: Row[]
  total: number
  page: number
  size: number
  topics: BoardTopic[]
  retrain_due_total: number
  stats: {
    month_sessions: number
    pass_rate: number
    makeup_people: number
    retrain_due_people: number
  }
}

const ENDPOINT = '/api/training'
const columns = ["培训编号", "培训主题", "培训讲师", "培训日期", "参训人数", "考核通过", "培训资料", "培训状态"]
const actions = ["组织培训", "登记考核", "安排补训"]

const rows = ref<Row[]>([])
const topics = ref<BoardTopic[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({ keyword: '', trainer: '', status: '', topic: '' })

const stats = computed(() => {
  const s = payload.value?.stats
  return [
    { label: `本月培训（${new Date().getMonth() + 1}月）`, value: s ? `${s.month_sessions} 场` : '—' },
    { label: '通过率', value: s ? formatPercent(s.pass_rate) : '—' },
    { label: '待补训人数', value: s ? `${s.makeup_people} 人` : '—' },
    { label: '复训到期人数', value: s ? `${s.retrain_due_people} 人` : '—' },
  ]
})

const payload = ref<ListPayload | null>(null)

function formatPercent(value: number): string {
  return `${Math.round(value * 1000) / 10}%`
}

function selectTopic(topic: string) {
  // 再次点击已选主题相当于取消；切换主题后明细立即只看该主题
  filters.value.topic = filters.value.topic === topic ? '' : topic
  void reload()
}

function clearTopic() {
  filters.value.topic = ''
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', trainer: '', status: '', topic: '' }
  void reload()
}

function exportRows() {
  const query = new URLSearchParams(buildParams()).toString()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function buildParams(): Record<string, string> {
  const params: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters.value)) {
    if (value && value.trim()) {
      params[key] = value.trim()
    }
  }
  return params
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
  // 看板与明细共用这一次请求返回的数据，避免两处口径不一致
  const query = new URLSearchParams(buildParams()).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('培训记录列表读取失败')
    }
    const data = (await response.json()) as ListPayload
    payload.value = data
    rows.value = data.items ?? []
    topics.value = data.topics ?? []
    total.value = data.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '安全培训列表读取失败'
  }
}

onMounted(reload)
</script>
