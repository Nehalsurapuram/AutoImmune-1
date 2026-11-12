package com.autoimmune.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F12 target test: Sensitive Actuator endpoint /actuator/env must not be exposed (404). */
@SpringBootTest
@AutoConfigureMockMvc
class F12TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void envActuatorEndpointIsNotExposed() throws Exception {
        mvc.perform(get("/actuator/env"))
                .andExpect(status().isNotFound());
    }
}
