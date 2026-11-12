package com.autoimmune.orders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

/** F13 target test: Querying non-existent order must return HTTP 404 Not Found, not HTTP 500. */
@SpringBootTest
@AutoConfigureMockMvc
class F13TargetTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void missingOrderReturns404NotFound() throws Exception {
        mvc.perform(get("/api/orders/999/total"))
                .andExpect(status().isNotFound());
    }
}
