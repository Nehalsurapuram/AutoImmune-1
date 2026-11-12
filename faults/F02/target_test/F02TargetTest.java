package com.autoimmune.orders;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F02: customer search must be case-insensitive; searching for 'ALICE' must find orders for 'alice'. */
@SpringBootTest
@AutoConfigureMockMvc
class F02TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void searchCustomerIsCaseInsensitive() throws Exception {
        mvc.perform(get("/api/orders/search").param("customer", "ALICE"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].customer").value("alice"))
                .andExpect(jsonPath("$[1].customer").value("alice"));
    }
}
