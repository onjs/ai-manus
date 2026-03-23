<template>
  <div class="bg-[var(--background-gray-main)] sm:bg-[var(--background-menu-white)] sm:rounded-[22px] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)] border border-black/8 dark:border-[var(--border-light)] flex h-full w-full">
    <div class="flex-1 min-w-0 p-4 flex flex-col h-full">
      <div class="flex items-center gap-2 w-full">
        <div class="flex items-center gap-2 flex-1 min-w-0">
          <div class="text-[var(--text-primary)] text-lg font-semibold shrink-0">{{ $t('Manus Computer') }}</div>
          <div
            v-if="toolInfo"
            :title="`${toolInfo.function} ${toolInfo.functionArg || ''}`.trim()"
            class="max-w-[65%] w-[max-content] min-w-0 h-8 truncate text-[13px] rounded-full inline-flex items-center px-[10px] py-[3px] border border-[var(--border-light)] bg-[var(--fill-tsp-gray-main)] text-[var(--text-secondary)]"
          >
            <span class="truncate">{{ toolInfo.function }}</span>
            <span
              class="min-w-0 px-1 ml-1 text-[12px] font-mono max-w-full text-ellipsis overflow-hidden whitespace-nowrap text-[var(--text-tertiary)]"
            >
              <code>{{ toolInfo.functionArg }}</code>
            </span>
          </div>
        </div>
        <button
          class="w-7 h-7 relative rounded-md inline-flex items-center justify-center gap-2.5 cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]">
          <Minimize2 class="w-5 h-5 text-[var(--icon-tertiary)]" @click="hide" />
        </button>
      </div>
      <div
        class="flex flex-col rounded-[12px] overflow-hidden bg-[var(--background-gray-main)] border border-[var(--border-dark)] dark:border-black/30 shadow-[0px_4px_32px_0px_rgba(0,0,0,0.04)] flex-1 min-h-0 mt-[12px]">
        <component v-if="toolInfo" :is="toolInfo.view" :live="live" :sessionId="sessionId"
          :toolContent="toolContent" :isShare="isShare" />
        <div class="mt-auto flex w-full items-center gap-2 px-4 h-[44px] relative" v-if="!realTime">
          <button
            class="h-10 px-3 border border-[var(--border-main)] flex items-center gap-1 bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] rounded-full cursor-pointer absolute left-[50%] translate-x-[-50%]"
            style="bottom: calc(100% + 10px);" @click="jumpToRealTime">
            <PlayIcon :size="16" />
            <span class="text-[var(--text-primary)] text-sm font-medium">{{ $t('Jump to live') }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue';
import { Minimize2, PlayIcon } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import { useToolInfo } from '@/composables/useTool';

const props = defineProps<{
  sessionId?: string;
  realTime: boolean;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
}>();

const { toolInfo } = useToolInfo(toRef(props, 'toolContent'));

const emit = defineEmits<{
  (e: 'jumpToRealTime'): void,
  (e: 'hide'): void
}>();

const hide = () => {
  emit('hide');
};


const jumpToRealTime = () => {
  emit('jumpToRealTime');
};
</script>
