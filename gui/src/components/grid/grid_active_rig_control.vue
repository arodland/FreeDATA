<script setup lang="ts">
import { setActivePinia } from "pinia";
import pinia from "../../store/index";
import { setRadioParameters } from "../../js/api";
setActivePinia(pinia);

import { useStateStore } from "../../store/stateStore.js";
const state = useStateStore(pinia);

function set_radio_parameters() {
  setRadioParameters(state.frequency, state.mode, state.rf_level);
}
</script>

<template>
  <div class="card h-100">
    <div class="card-header p-0">
      <i class="bi bi-house-door" style="font-size: 1.2rem"></i>&nbsp;
      <strong>Radio control</strong>
    </div>

    <div class="card-body overflow-auto p-0">
      <div class="input-group input-group-sm bottom-0 m-0">
        <div class="me-2">
          <div class="input-group input-group-sm">
            <span class="input-group-text">QRG</span>
            <span class="input-group-text"
              >{{ state.frequency / 1000 }} kHz</span
            >

            <button
              class="btn btn-secondary dropdown-toggle"
              v-bind:class="{
                disabled: state.hamlib_status === 'disconnected',
              }"
              type="button"
              data-bs-toggle="offcanvas"
              data-bs-target="#offcanvasFrequency"
              aria-controls="offcanvasExample"
            ></button>
          </div>
        </div>

        <div class="me-2">
          <div class="input-group input-group-sm">
            <span class="input-group-text">Mode</span>
            <select
              class="form-control"
              v-model="state.mode"
              @click="set_radio_parameters()"
              v-bind:class="{
                disabled: state.hamlib_status === 'disconnected',
              }"
            >
              <option value="USB">USB</option>
              <option value="LSB">LSB</option>
              <option value="PKTUSB">PKT-U</option>
              <option value="PKTLSB">PKT-L</option>
              <option value="AM">AM</option>
              <option value="FM">FM</option>
              <option value="PKTFM">PKTFM</option>
            </select>
          </div>
        </div>

        <div class="me-2">
          <div class="input-group input-group-sm">
            <span class="input-group-text">% Power</span>
            <select
              class="form-control"
              v-model="state.rf_level"
              @click="set_radio_parameters()"
              v-bind:class="{
                disabled: state.hamlib_status === 'disconnected',
              }"
            >
              <option value="0">-</option>
              <option value="10">10</option>
              <option value="20">20</option>
              <option value="30">30</option>
              <option value="40">40</option>
              <option value="50">50</option>
              <option value="60">60</option>
              <option value="70">70</option>
              <option value="80">80</option>
              <option value="90">90</option>
              <option value="100">100</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
