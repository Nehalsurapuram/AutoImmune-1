package com.autoimmune.orders;

import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F05: API contract requires item records to serialize quantity as key 'qty', not 'quantity'. */
@SpringBootTest
@AutoConfigureMockMvc
class F05TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void itemsSerializeQtyKey() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].items[0].qty", notNullValue()))
                .andExpect(jsonPath("$[0].items[0].qty").value(1));
    }
}
