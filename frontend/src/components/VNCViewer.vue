<template>
  <div
    ref="vncContainer"
    class="vnc-container">
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted, watch, nextTick } from 'vue';
import { getVNCUrl } from '@/api/agent';
// @ts-ignore
import RFB from '@novnc/novnc/lib/rfb';

const props = defineProps<{
  sessionId: string;
  enabled?: boolean;
  viewOnly?: boolean;
}>();

const emit = defineEmits<{
  connected: [];
  disconnected: [reason?: any];
  credentialsRequired: [];
}>();

const vncContainer = ref<HTMLDivElement | null>(null);
let rfb: RFB | null = null;
let resizeObserver: ResizeObserver | null = null;
let resizeRaf: number | null = null;

const refreshViewport = () => {
  if (!rfb) return;
  rfb.scaleViewport = true;
  rfb.clipViewport = false;
  // noVNC only listens to window resize by default; force reflow when panel size changes.
  const resizeFn = (rfb as any)?._windowResize;
  if (typeof resizeFn === 'function') {
    resizeFn.call(rfb);
  }
};

const scheduleRefreshViewport = () => {
  if (resizeRaf !== null) {
    cancelAnimationFrame(resizeRaf);
  }
  resizeRaf = requestAnimationFrame(() => {
    resizeRaf = null;
    refreshViewport();
  });
};

const initVNCConnection = async () => {
  if (!vncContainer.value || !props.enabled) return;

  // Disconnect existing connection
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }

  try {
    const wsUrl = await getVNCUrl(props.sessionId);

    // Create NoVNC connection
    rfb = new RFB(vncContainer.value, wsUrl, {
      credentials: { password: '' },
      shared: true,
      repeaterID: '',
      wsProtocols: ['binary'],
      // Scaling options
      scaleViewport: true,  // Automatically scale to fit container
      //resizeSession: true   // Request server to adjust resolution
    });

    // Set viewOnly based on props, default to false (interactive)
    rfb.viewOnly = props.viewOnly ?? false;
    rfb.scaleViewport = true;
    rfb.clipViewport = false;
    //rfb.resizeSession = true;

    rfb.addEventListener('connect', () => {
      console.log('VNC connection successful');
      // Run once now and once after layout settles to avoid right-edge clipping.
      scheduleRefreshViewport();
      setTimeout(scheduleRefreshViewport, 120);
      emit('connected');
    });

    rfb.addEventListener('disconnect', (e: any) => {
      console.log('VNC connection disconnected', e);
      emit('disconnected', e);
    });

    rfb.addEventListener('credentialsrequired', () => {
      console.log('VNC credentials required');
      emit('credentialsRequired');
    });
  } catch (error) {
    console.error('Failed to initialize VNC connection:', error);
  }

  await nextTick();
  scheduleRefreshViewport();
};

const disconnect = () => {
  if (rfb) {
    rfb.disconnect();
    rfb = null;
  }
};

// Watch for session ID or enabled state changes
watch([() => props.sessionId, () => props.enabled], () => {
  if (props.enabled && vncContainer.value) {
    initVNCConnection();
  } else {
    disconnect();
  }
}, { immediate: true });

// Watch for container availability
watch(vncContainer, () => {
  if (vncContainer.value && props.enabled) {
    initVNCConnection();
  }
});

onMounted(() => {
  if (typeof ResizeObserver === 'undefined') return;
  resizeObserver = new ResizeObserver(() => {
    scheduleRefreshViewport();
  });
  if (vncContainer.value) {
    resizeObserver.observe(vncContainer.value);
  }
});

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (resizeRaf !== null) {
    cancelAnimationFrame(resizeRaf);
    resizeRaf = null;
  }
  disconnect();
});

// Expose methods for parent component
defineExpose({
  disconnect,
  initConnection: initVNCConnection
});
</script>

<style scoped>
.vnc-container {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: rgb(40, 40, 40);
  align-items: center;
  justify-content: center;
}

:deep(canvas) {
  max-width: 100%;
  max-height: 100%;
}
</style>
