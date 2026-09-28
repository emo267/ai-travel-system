<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">我的行程</h2>
        <p class="page-sub">
          共 {{ tasks.length }} 份行程
          <template v-if="filtered.length !== tasks.length">，当前筛选出 {{ filtered.length }} 份</template>
        </p>
      </div>
      <el-button type="primary" :icon="Plus" @click="router.push('/travel/create')">
        创建行程
      </el-button>
    </div>

    <div v-if="tasks.length" class="toolbar surface">
      <el-input
        v-model="keyword"
        class="toolbar__search"
        placeholder="搜索目的地"
        :prefix-icon="Search"
        clearable
      />
      <el-select v-model="statusFilter" class="toolbar__field" placeholder="全部状态">
        <el-option label="全部状态" value="" />
        <el-option v-for="s in STATUS_LIST" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-select v-model="sortBy" class="toolbar__field">
        <el-option label="最近创建" value="created" />
        <el-option label="出发日期最近" value="start" />
        <el-option label="预算从高到低" value="budget" />
      </el-select>
      <span v-if="polling" class="toolbar__live">
        <el-icon class="is-spin" :size="13"><Loading /></el-icon>有行程正在生成，自动刷新中
      </span>
    </div>

    <el-row v-if="loading" :gutter="18">
      <el-col v-for="n in 6" :key="n" :xs="24" :sm="12" :lg="8" class="cell">
        <div class="surface skeleton">
          <el-skeleton animated>
            <template #template>
              <el-skeleton-item variant="image" style="height: 116px; border-radius: 0" />
              <div style="padding: 14px 16px 18px">
                <el-skeleton-item variant="h3" style="width: 52%" />
                <el-skeleton-item variant="text" style="margin-top: 12px; width: 78%" />
                <el-skeleton-item variant="text" style="margin-top: 8px; width: 60%" />
              </div>
            </template>
          </el-skeleton>
        </div>
      </el-col>
    </el-row>

    <el-empty v-else-if="!tasks.length" :image-size="120" description="还没有行程，先创建一份吧">
      <el-button type="primary" :icon="Plus" @click="router.push('/travel/create')">
        创建我的第一份行程
      </el-button>
    </el-empty>

    <el-empty v-else-if="!filtered.length" :image-size="110" description="没有符合筛选条件的行程">
      <el-button @click="resetFilters">清空筛选条件</el-button>
    </el-empty>

    <el-row v-else :gutter="18">
      <el-col v-for="task in filtered" :key="task.task_id" :xs="24" :sm="12" :lg="8" class="cell">
        <TravelCard :task="task" @open="goDetail" @delete="handleDelete" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Plus, Search } from '@element-plus/icons-vue'
import TravelCard from '../components/TravelCard.vue'
import { deleteTask, getTasks } from '../api/travel'
import { STATUS_LIST, isFinished } from '../utils/format'

const POLL_INTERVAL = 6000

const router = useRouter()
const tasks = ref([])
const loading = ref(true)
const keyword = ref('')
const statusFilter = ref('')
const sortBy = ref('created')
const polling = ref(false)

let timer = null

const syncPolling = () => {
  const hasUnfinished = tasks.value.some((t) => !isFinished(t.status))
  polling.value = hasUnfinished

  if (hasUnfinished && !timer) {
    timer = setInterval(() => fetchTasks({ silent: true }), POLL_INTERVAL)
  } else if (!hasUnfinished && timer) {
    clearInterval(timer)
    timer = null
  }
}

const fetchTasks = async ({ silent = false } = {}) => {
  if (!silent) loading.value = true
  try {
    tasks.value = await getTasks()
  } catch {
    // 失败提示由 axios 响应拦截器统一弹出
  } finally {
    if (!silent) loading.value = false
    syncPolling()
  }
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const list = tasks.value.filter((task) => {
    const hitKeyword = !kw || String(task.destination).toLowerCase().includes(kw)
    const hitStatus = !statusFilter.value || task.status === statusFilter.value
    return hitKeyword && hitStatus
  })

  const sorters = {
    created: (a, b) => new Date(b.create_time) - new Date(a.create_time),
    start: (a, b) => new Date(a.start_date) - new Date(b.start_date),
    budget: (a, b) => (Number(b.total_budget) || 0) - (Number(a.total_budget) || 0),
  }
  return [...list].sort(sorters[sortBy.value] || sorters.created)
})

const resetFilters = () => {
  keyword.value = ''
  statusFilter.value = ''
}

const goDetail = (id) => router.push(`/travel/detail/${id}`)

const handleDelete = async (task) => {
  try {
    await ElMessageBox.confirm(
      `确定删除「${task.destination}」这份行程吗？删除后无法恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }

  try {
    await deleteTask(task.task_id)
    ElMessage.success('已删除')
    fetchTasks({ silent: true })
  } catch {
    // 失败提示由拦截器处理
  }
}

fetchTasks()

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 14px 16px;
  margin-bottom: 20px;
}

.toolbar__search {
  width: 260px;
}

.toolbar__field {
  width: 150px;
}

.toolbar__live {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  color: var(--brand-600);
  font-size: 12.5px;
}

.is-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.cell {
  margin-bottom: 18px;
}

.skeleton {
  height: 100%;
  overflow: hidden;
}

@media (max-width: 640px) {
  .toolbar__search,
  .toolbar__field {
    width: 100%;
  }

  .toolbar__live {
    margin-left: 0;
  }
}
</style>
