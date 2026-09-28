<template>
  <div class="map-wrap">
    <div v-show="!error" ref="containerRef" class="map-canvas" :style="{ height: height + 'px' }"></div>

    <div v-if="error" class="map-fallback" :style="{ height: height + 'px' }">
      <el-icon :size="26"><MapLocation /></el-icon>
      <p>{{ error }}</p>
      <small>请检查 frontend/.env 的 VITE_AMAP_KEY 与高德控制台绑定的安全域名</small>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { MapLocation } from '@element-plus/icons-vue'
import { normalizeSpots } from '../utils/format'
import { useTheme } from '../utils/theme'

const MAP_STYLE = { light: 'amap://styles/normal', dark: 'amap://styles/dark' }

const props = defineProps({
  itinerary: { type: Array, default: () => [] },
  destination: { type: String, default: '' },
  height: { type: Number, default: 380 },
})

const { isDark } = useTheme()

const containerRef = ref(null)
const error = ref('')
let map = null
let disposed = false

const spotNames = () => {
  const names = []
  // 景点在新方案里是对象（含门票、时间），老方案里是纯字符串，统一取名称
  props.itinerary?.forEach((day) => {
    normalizeSpots(day?.spots).forEach((spot) => spot.name && names.push(spot.name))
  })
  return [...new Set(names)]
}

const applyStyle = () => {
  try {
    map?.setMapStyle(MAP_STYLE[isDark.value ? 'dark' : 'light'])
  } catch (e) {
    console.warn('地图主题切换失败', e)
  }
}

onMounted(async () => {
  const key = import.meta.env.VITE_AMAP_KEY
  if (!key) {
    error.value = '未配置高德地图 Key'
    return
  }

  const spots = spotNames()
  const targets = spots.length ? spots : [props.destination].filter(Boolean)
  if (!targets.length) {
    error.value = '暂无可定位的景点数据'
    return
  }

  window._AMapSecurityConfig = {
    securityJsCode: import.meta.env.VITE_AMAP_SECURITY_CODE,
  }

  try {
    const AMap = await AMapLoader.load({
      key,
      version: '2.0',
      plugins: ['AMap.PlaceSearch'],
    })
    if (disposed || !containerRef.value) return

    map = new AMap.Map(containerRef.value, {
      zoom: 11,
      mapStyle: MAP_STYLE[isDark.value ? 'dark' : 'light'],
    })

    // PlaceSearch 不挂 map，避免它自动打点后再叠加一次手动 marker
    const placeSearch = new AMap.PlaceSearch({ pageSize: 5 })
    let pending = targets.length
    const settle = () => {
      if (--pending === 0 && map) map.setFitView()
    }

    targets.forEach((name) => {
      placeSearch.search(name, (status, result) => {
        const poi = status === 'complete' ? result?.poiList?.pois?.[0] : null
        if (poi?.location && map) {
          map.add(
            new AMap.Marker({
              position: [poi.location.lng, poi.location.lat],
              title: name,
            })
          )
        }
        settle()
      })
    })
  } catch (e) {
    console.error('高德地图加载失败', e)
    error.value = '地图加载失败'
  }
})

watch(isDark, applyStyle)

onBeforeUnmount(() => {
  disposed = true
  map?.destroy()
  map = null
})
</script>

<style scoped>
.map-wrap {
  position: relative;
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--border-1);
  background: var(--bg-soft);
}

.map-canvas {
  width: 100%;
}

.map-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 24px;
  text-align: center;
  color: var(--text-3);
}

.map-fallback p {
  margin: 0;
  font-size: 14px;
  color: var(--text-2);
}

.map-fallback small {
  font-size: 12px;
}
</style>
