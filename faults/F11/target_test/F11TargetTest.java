package com.autoimmune.orders;

import static org.hamcrest.Matchers.greaterThan;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F11 target test: Order 1 item quantities must be positive and total must be 950.00. */
@SpringBootTest
@AutoConfigureMockMvc
class F11TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void order1TotalMatchesExpectedPositiveItemQuantities() throws Exception {
        mvc.perform(get("/api/orders/1/total"))
                .andExpect(status().isOk())
                .andExpect(content().string("950.00"));

        mvc.perform(get("/api/orders/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].qty", greaterThan(0)))
                .andExpect(jsonPath("$.items[1].qty", greaterThan(0)));
    }
}
