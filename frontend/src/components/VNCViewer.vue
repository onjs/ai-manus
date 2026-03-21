<template>
  <div
    ref="vncContainer"
    class="vnc-container"
    style="display: flex; width: 100%; height: 100%; overflow: auto; background: rgb(40, 40, 40);">
  </div>
</template>

<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted, watch } from 'vue';
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
let lifecycleVersion = 0;

const safeDisconnect = (instance: RFB | null) => {
  if (!instance) return;
  try {
    const state = (instance as any)._rfbConnectionState;
    if (state !== 'disconnected') {
      instance.disconnect();
    }
  } catch (error) {
    console.warn('VNC disconnect skipped due to stale/disconnected state', error);
  }
};

const initVNCConnection = async () => {
  if (!vncContainer.value || !props.enabled) return;

  const version = ++lifecycleVersion;
  const previous = rfb;
  rfb = null;
  safeDisconnect(previous);

  try {
    const wsUrl = await getVNCUrl(props.sessionId);
    if (version !== lifecycleVersion || !vncContainer.value || !props.enabled) return;

    // Create NoVNC connection
    const instance = new RFB(vncContainer.value, wsUrl, {
      credentials: { password: '' },
      shared: true,
      repeaterID: '',
      wsProtocols: ['binary'],
      // Scaling options
      scaleViewport: true,  // Automatically scale to fit container
      //resizeSession: true   // Request server to adjust resolution
    });

    // Set viewOnly based on props, default to false (interactive)
    rfb = instance;
    instance.viewOnly = props.viewOnly ?? false;
    instance.scaleViewport = true;
    //rfb.resizeSession = true;

    instance.addEventListener('connect', () => {
      if (rfb !== instance) return;
      console.log('VNC connection successful');
      emit('connected');
    });

    instance.addEventListener('disconnect', (e: any) => {
      if (rfb === instance) {
        rfb = null;
      }
      console.log('VNC connection disconnected', e);
      emit('disconnected', e);
    });

    instance.addEventListener('credentialsrequired', () => {
      if (rfb !== instance) return;
      console.log('VNC credentials required');
      emit('credentialsRequired');
    });
  } catch (error) {
    if (version !== lifecycleVersion) return;
    console.error('Failed to initialize VNC connection:', error);
  }
};

const disconnect = () => {
  lifecycleVersion += 1;
  const current = rfb;
  rfb = null;
  safeDisconnect(current);
};

// Watch for session ID / enabled / view-only changes
watch([() => props.sessionId, () => props.enabled, () => props.viewOnly], () => {
  if (props.enabled && vncContainer.value) {
    initVNCConnection();
  } else {
    disconnect();
  }
});

onMounted(() => {
  if (props.enabled && vncContainer.value) {
    initVNCConnection();
  }
});

onBeforeUnmount(() => {
  disconnect();
});

// Expose methods for parent component
defineExpose({
  disconnect,
  initConnection: initVNCConnection
});
</script>

<style scoped>
</style>
