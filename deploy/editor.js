export default {
  template: `
    <q-editor ref="qRef" :id="id" v-model="inputValue" :toolbar="editorToolbar" :fonts="editorFonts">
      <template v-for="(_, slot) in $slots" v-slot:[slot]="slotProps">
        <slot :name="slot" v-bind="slotProps || {}" />
      </template>
    </q-editor>
  `,
  props: {
    value: String,
    id: String,
  },
  data() {
    return {
      inputValue: this.value,
      emitting: true,
      editorToolbar: [
        ["bold", "italic", "underline", "strike"],
        ["unordered", "ordered", "outdent", "indent"],
        ["left", "center", "right", "justify"],
        ["link", "hr"],
        ["undo", "redo"],
        ["removeFormat", "viewsource"]
      ],
      editorFonts: {}
    };
  },
  beforeUnmount() {
    const element = mounted_app.elements[this.$props.id.slice(1)];
    if (element) element.props.value = this.inputValue;
  },
  watch: {
    value(newValue) {
      this.emitting = false;
      this.inputValue = newValue;
      this.$nextTick(() => (this.emitting = true));
    },
    inputValue(newValue) {
      if (!this.emitting) return;
      this.$emit("update:value", newValue);
    },
  },
  methods: {
    updateValue() {
      this.inputValue = this.value;
    },
  },
};
