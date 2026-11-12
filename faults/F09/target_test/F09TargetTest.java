package com.autoimmune.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F09 target test: Total calculation returns exact value 950.00 for order 1. */
@SpringBootTest
@AutoConfigureMockMvc
class F09TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void totalCalculationProducesCorrectValue() throws Exception {
        mvc.perform(get("/api/orders/1/total"))
                .andExpect(status().isOk())
                .andExpect(content().string("950.00"));
    }
}
